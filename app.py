from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import re
from PIL import Image, ExifTags

app = Flask(__name__)

# Configure upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['METADATA_FILE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.json')

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def extract_ai_metadata(image_path):
    """Extract metadata from AI-generated images"""
    try:
        img = Image.open(image_path)
        metadata = {}
        
        # Extract metadata from PNG parameters
        if 'parameters' in img.info:
            params = img.info['parameters']
            parsed = parse_metadata_string(params)
            metadata.update(parsed)
            print(f"Extracted PNG parameters: {list(parsed.keys())}")
        
        # Extract metadata from PNG text chunks
        if hasattr(img, 'text') and img.text:
            for key, value in img.text.items():
                if key.lower() in ['comment', 'description', 'parameters', 'prompt']:
                    parsed = parse_metadata_string(value)
                    # Only update if we don't already have these values
                    for k, v in parsed.items():
                        if not metadata.get(k) and v:
                            metadata[k] = v
                    print(f"Extracted PNG text chunk {key}: {list(parsed.keys())}")
                    
                # Handle specific keys that might contain useful information
                if key.lower() == 'software' and 'stable diffusion' in value.lower():
                    metadata['tools'] = ['Stable Diffusion']
                    
                # Store raw text chunks for debugging
                metadata[f'text_{key}'] = value
        
        # Extract metadata from EXIF data
        if hasattr(img, '_getexif') and img._getexif():
            exif = {
                ExifTags.TAGS.get(tag, tag): value
                for tag, value in img._getexif().items()
            }
            
            # Look for metadata in UserComment or ImageDescription
            for key in ['UserComment', 'ImageDescription']:
                if key in exif and exif[key]:
                    try:
                        # Sometimes UserComment is encoded
                        comment = exif[key]
                        if isinstance(comment, bytes):
                            comment = comment.decode('utf-8', errors='ignore')
                        
                        parsed = parse_metadata_string(comment)
                        # Only update if we don't already have these values
                        for k, v in parsed.items():
                            if not metadata.get(k) and v:
                                metadata[k] = v
                        print(f"Extracted EXIF {key}: {list(parsed.keys())}")
                    except Exception as e:
                        print(f"Error parsing EXIF {key}: {e}")
        
        # Extract metadata from XMP data
        if hasattr(img, 'applist'):
            for segment, content in img.applist:
                if segment == 'APP1' and b'http://ns.adobe.com/xap/1.0/' in content:
                    try:
                        xmp_start = content.find(b'<x:xmpmeta')
                        xmp_end = content.find(b'</x:xmpmeta')
                        if xmp_start != -1 and xmp_end != -1:
                            xmp_str = content[xmp_start:xmp_end+12].decode('utf-8', errors='ignore')
                            # Look for description tags
                            import re
                            desc_match = re.search(r'<dc:description>(.*?)</dc:description>', xmp_str, re.DOTALL)
                            if desc_match:
                                desc = desc_match.group(1)
                                parsed = parse_metadata_string(desc)
                                # Only update if we don't already have these values
                                for k, v in parsed.items():
                                    if not metadata.get(k) and v:
                                        metadata[k] = v
                                print(f"Extracted XMP description: {list(parsed.keys())}")
                    except Exception as e:
                        print(f"Error parsing XMP data: {e}")
        
        # Look for Fooocus metadata in PNG tEXt chunks
        if hasattr(img, 'text') and img.text:
            fooocus_keys = ['fooocus_prompt', 'fooocus_negative_prompt', 'fooocus_seed', 'fooocus_cfg']
            for key in fooocus_keys:
                if key in img.text:
                    if key == 'fooocus_prompt' and not metadata.get('prompt'):
                        metadata['prompt'] = img.text[key]
                    elif key == 'fooocus_negative_prompt' and not metadata.get('negative_prompt'):
                        metadata['negative_prompt'] = img.text[key]
                    elif key == 'fooocus_seed' and not metadata.get('seed'):
                        metadata['seed'] = img.text[key]
                    elif key == 'fooocus_cfg' and not metadata.get('cfg_scale'):
                        metadata['cfg_scale'] = img.text[key]
        
        # Handle ComfyUI workflow JSON
        if hasattr(img, 'text') and img.text.get('prompt'):
            try:
                prompt_text = img.text.get('prompt')
                if prompt_text and '{' in prompt_text and '}' in prompt_text:
                    # Try to parse as JSON
                    workflow_data = json.loads(prompt_text)
                    
                    # Extract data from ComfyUI workflow
                    if isinstance(workflow_data, dict):
                        print("Detected ComfyUI workflow JSON")
                        
                        # Find KSampler node
                        ksampler_node = None
                        checkpoint_node = None
                        positive_prompt_node = None
                        negative_prompt_node = None
                        
                        for node_id, node_data in workflow_data.items():
                            if isinstance(node_data, dict) and 'class_type' in node_data:
                                if node_data['class_type'] == 'KSampler':
                                    ksampler_node = node_data
                                elif node_data['class_type'] in ['CheckpointLoaderSimple', 'CheckpointLoader']:
                                    checkpoint_node = node_data
                                elif node_data['class_type'] == 'CLIPTextEncode':
                                    # Check if this is a positive or negative prompt node
                                    if 'inputs' in node_data and 'text' in node_data['inputs']:
                                        text = node_data['inputs']['text']
                                        if text and not text.strip().startswith('(') and not text.strip().startswith('['):
                                            positive_prompt_node = node_data
                                        elif not text or text.strip() == '':
                                            negative_prompt_node = node_data
                        
                        # Extract data from KSampler node
                        if ksampler_node and 'inputs' in ksampler_node:
                            inputs = ksampler_node['inputs']
                            if 'seed' in inputs and not metadata.get('seed'):
                                metadata['seed'] = str(inputs['seed'])
                            if 'steps' in inputs and not metadata.get('steps'):
                                metadata['steps'] = str(inputs['steps'])
                            if 'cfg' in inputs and not metadata.get('cfg_scale'):
                                metadata['cfg_scale'] = str(inputs['cfg'])
                            if 'sampler_name' in inputs and not metadata.get('sampler'):
                                metadata['sampler'] = inputs['sampler_name']
                            if 'scheduler' in inputs and not metadata.get('schedule_type'):
                                metadata['schedule_type'] = inputs['scheduler']
                        
                        # Extract data from checkpoint node
                        if checkpoint_node and 'inputs' in checkpoint_node:
                            inputs = checkpoint_node['inputs']
                            if 'ckpt_name' in inputs and not metadata.get('model_name'):
                                model_name = inputs['ckpt_name']
                                # Remove quotes if present
                                if model_name.startswith('"') and model_name.endswith('"'):
                                    model_name = model_name[1:-1]
                                if model_name.endswith('.safetensors'):
                                    model_name = model_name[:-12]  # Remove .safetensors extension
                                metadata['model_name'] = model_name
                                metadata['model'] = model_name
                        
                        # Extract prompts
                        if positive_prompt_node and 'inputs' in positive_prompt_node:
                            if 'text' in positive_prompt_node['inputs'] and not metadata.get('prompt'):
                                metadata['prompt'] = positive_prompt_node['inputs']['text']
                        
                        if negative_prompt_node and 'inputs' in negative_prompt_node:
                            if 'text' in negative_prompt_node['inputs'] and not metadata.get('negative_prompt'):
                                metadata['negative_prompt'] = negative_prompt_node['inputs']['text']
                        
                        # Set ComfyUI as the tool
                        metadata['tools'] = ['ComfyUI']
            except Exception as e:
                print(f"Error parsing ComfyUI workflow: {e}")
        
        # Handle simple metadata string format
        if not metadata.get('prompt') and hasattr(img, 'text') and img.text.get('parameters') == 'None' and img.text.get('prompt'):
            try:
                prompt_text = img.text.get('prompt')
                if prompt_text and isinstance(prompt_text, str):
                    # Check if it's a JSON string
                    if prompt_text.strip().startswith('{') and prompt_text.strip().endswith('}'):
                        try:
                            # Try to parse as JSON
                            json_data = json.loads(prompt_text)
                            # Process JSON data here
                        except:
                            # Not valid JSON, treat as plain text
                            metadata['prompt'] = prompt_text
                    else:
                        # Plain text prompt
                        metadata['prompt'] = prompt_text
            except Exception as e:
                print(f"Error parsing simple metadata: {e}")
        
        # Process workflow data if present
        if hasattr(img, 'text') and img.text.get('workflow'):
            try:
                workflow_text = img.text.get('workflow')
                if workflow_text and isinstance(workflow_text, str):
                    if workflow_text.strip().startswith('{') and workflow_text.strip().endswith('}'):
                        # Try to parse as JSON
                        workflow_data = json.loads(workflow_text)
                        if isinstance(workflow_data, dict) and 'nodes' in workflow_data:
                            print("Found workflow data with nodes")
                            # Process nodes to extract metadata
                            for node in workflow_data['nodes']:
                                if isinstance(node, dict) and 'type' in node:
                                    # Extract data based on node type
                                    if node['type'] in ['CheckpointLoaderSimple', 'CheckpointLoader'] and 'widgets_values' in node:
                                        if len(node['widgets_values']) > 0 and not metadata.get('model_name'):
                                            model_name = node['widgets_values'][0]
                                            # Remove quotes if present
                                            if model_name.startswith('"') and model_name.endswith('"'):
                                                model_name = model_name[1:-1]
                                            if model_name.endswith('.safetensors'):
                                                model_name = model_name[:-12]
                                            metadata['model_name'] = model_name
                                            metadata['model'] = model_name
                                    
                                    elif node['type'] == 'KSampler' and 'widgets_values' in node:
                                        values = node['widgets_values']
                                        if len(values) >= 7:
                                            if not metadata.get('seed'):
                                                metadata['seed'] = str(values[0])
                                            if not metadata.get('steps'):
                                                metadata['steps'] = str(values[2])
                                            if not metadata.get('cfg_scale'):
                                                metadata['cfg_scale'] = str(values[3])
                                            if not metadata.get('sampler'):
                                                metadata['sampler'] = str(values[4])
                                            if not metadata.get('schedule_type'):
                                                metadata['schedule_type'] = str(values[5])
                                    
                                    elif node['type'] == 'CLIPTextEncode' and 'widgets_values' in node:
                                        if len(node['widgets_values']) > 0:
                                            text = node['widgets_values'][0]
                                            if 'title' in node:
                                                if node['title'] == 'Positive Prompt' and not metadata.get('prompt'):
                                                    metadata['prompt'] = text
                                                elif node['title'] == 'Negative Prompt' and not metadata.get('negative_prompt'):
                                                    metadata['negative_prompt'] = text
                                            elif not metadata.get('prompt') and text and text.strip() != '':
                                                metadata['prompt'] = text
            except Exception as e:
                print(f"Error parsing workflow data: {e}")
        
        # Clean up model name if it has quotes
        if metadata.get('model_name'):
            model_name = metadata['model_name']
            if model_name.startswith('"') and model_name.endswith('"'):
                metadata['model_name'] = model_name[1:-1]
            if metadata.get('model'):
                model = metadata['model']
                if model.startswith('"') and model.endswith('"'):
                    metadata['model'] = model[1:-1]
        
        # Ensure we have a model name
        if not metadata.get('model_name') and metadata.get('model'):
            metadata['model_name'] = metadata['model']
        elif not metadata.get('model') and metadata.get('model_name'):
            metadata['model'] = metadata['model_name']
        
        # Add default values for missing fields
        defaults = {
            'prompt': 'No prompt found',
            'negative_prompt': 'No negative prompt found',
            'model_name': 'Unknown model',
            'steps': '20',
            'sampler': 'Unknown',
            'cfg_scale': '7',
            'seed': '0',
            'size': '512x512',
        }
        
        for key, default_value in defaults.items():
            if not metadata.get(key):
                metadata[key] = default_value
        
        # Preserve NSFW detection functionality
        # Check if the prompt or image content suggests NSFW content
        is_nsfw = False
        nsfw_keywords = ['nsfw', 'nude', 'naked', 'sex', 'porn', 'adult', 'xxx', 'erotic', 'explicit']
        
        # Check prompt for NSFW content
        if metadata.get('prompt'):
            prompt_lower = metadata.get('prompt').lower()
            if any(keyword in prompt_lower for keyword in nsfw_keywords):
                is_nsfw = True
                print("NSFW content detected in prompt")
        
        # Store NSFW flag in metadata
        metadata['is_nsfw'] = is_nsfw
        
        return metadata
    
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        import traceback
        traceback.print_exc()
        return {
            'prompt': 'Error extracting metadata',
            'negative_prompt': '',
            'model_name': 'Unknown model',
            'steps': '20',
            'sampler': 'Unknown',
            'cfg_scale': '7',
            'seed': '0',
            'size': '512x512',
        }

def parse_metadata_string(params_str):
    """Parse metadata string into a structured format"""
    metadata = {
        'prompt': '',
        'negative_prompt': '',
        'steps': '',
        'sampler': '',
        'cfg_scale': '',
        'seed': '',
        'size': '',
        'model': '',
        'model_name': '',
        'model_hash': '',
        'version': '',
        'clip_skip': '',
        'schedule_type': '',
        'distilled_cfg_scale': '',
    }
    
    try:
        # Check if this is empty
        if not params_str or params_str.strip() == '':
            return metadata
            
        print(f"Parsing metadata string: {params_str[:100]}...")
        
        # Check for LoRA tags in the prompt
        lora_tags = []
        if '<lora:' in params_str:
            import re
            lora_matches = re.findall(r'<lora:[^>]+>', params_str)
            for match in lora_matches:
                lora_tags.append(match)
                # Don't remove them from the prompt as they're part of it
        
        if lora_tags:
            metadata['lora_tags'] = ', '.join(lora_tags)
            print(f"Found LoRA tags: {lora_tags}")
        
        # First, check if this is a simple format with parameters at the end
        # This regex looks for a line that starts with "Steps:" or similar
        import re
        param_section_match = re.search(r'(?:^|\n)(Steps?:.*?)$', params_str, re.DOTALL)
        
        if param_section_match:
            # We found a parameter section
            param_section = param_section_match.group(1)
            
            # Extract the prompt (everything before the parameter section)
            prompt_text = params_str[:params_str.find(param_section)].strip()
            metadata['prompt'] = prompt_text
            
            # Now parse the parameter section
            param_lines = param_section.split(',')
            for param in param_lines:
                param = param.strip()
                if ':' in param:
                    key, value = [p.strip() for p in param.split(':', 1)]
                    key = key.lower()
                    
                    if 'step' in key:
                        metadata['steps'] = value
                    elif 'sampler' in key:
                        metadata['sampler'] = value
                    elif 'schedule type' in key:
                        metadata['schedule_type'] = value
                    elif key == 'cfg scale' or key == 'cfg':
                        metadata['cfg_scale'] = value
                    elif 'distilled cfg scale' in key:
                        metadata['distilled_cfg_scale'] = value
                    elif 'seed' in key:
                        metadata['seed'] = value
                    elif 'size' in key:
                        metadata['size'] = value
                    elif 'model hash' in key:
                        metadata['model_hash'] = value
                    elif key == 'model':
                        metadata['model'] = value
                        metadata['model_name'] = value
                    elif 'clip skip' in key:
                        metadata['clip_skip'] = value
                    elif 'version' in key:
                        metadata['version'] = value
                    elif 'module' in key:
                        # Store as additional parameter
                        metadata[f'module_{key.split()[1]}'] = value
            
            # Return early since we've handled this format
            return metadata
        
        # If we're here, it's not the simple format, so try the more complex parsing
        
        # Split by newlines first
        lines = params_str.split('\n')
        
        # If there's only one line, try to split by commas
        if len(lines) == 1:
            # Check if there are key-value pairs separated by commas
            if ':' in params_str and ',' in params_str:
                # Split the string at commas that are followed by a space and a word then a colon
                # This regex looks for: comma + optional whitespace + word + colon
                segments = re.split(r',\s*(?=[^,]+:)', params_str)
                lines = segments
        
        # Extract negative prompt if present
        negative_prompt_idx = -1
        for i, line in enumerate(lines):
            if 'negative prompt:' in line.lower() or 'negative prompt' in line.lower():
                negative_prompt_idx = i
                break
        
        if negative_prompt_idx >= 0:
            # Extract negative prompt text
            neg_prompt_line = lines[negative_prompt_idx]
            if ':' in neg_prompt_line:
                neg_prompt = neg_prompt_line.split(':', 1)[1].strip()
                metadata['negative_prompt'] = neg_prompt
                
                # Remove negative prompt line and any following lines until we hit a parameter
                param_lines = []
                param_started = False
                for i in range(negative_prompt_idx + 1, len(lines)):
                    if any(key in lines[i].lower() for key in ['steps:', 'sampler:', 'cfg scale:', 'seed:', 'size:', 'model:']):
                        param_started = True
                    
                    if param_started:
                        param_lines.append(lines[i])
                
                # Replace lines after negative prompt with just the parameter lines
                if param_lines:
                    lines = lines[:negative_prompt_idx] + param_lines
                else:
                    lines = lines[:negative_prompt_idx]
        
        # Look for parameter section marker
        param_start_idx = -1
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            if line_lower.startswith('steps:') or (line_lower.startswith('step') and ':' in line_lower):
                param_start_idx = i
                break
        
        # Extract prompt - everything before the parameter section
        if param_start_idx > 0:
            prompt_lines = lines[:param_start_idx]
            # Filter out any lines that look like parameters
            prompt_lines = [line for line in prompt_lines if not any(key in line.lower() for key in ['negative prompt:', 'steps:', 'sampler:', 'cfg scale:', 'seed:', 'size:', 'model:'])]
            if prompt_lines:
                metadata['prompt'] = '\n'.join(prompt_lines).strip()
        else:
            # If no parameter section found, try to extract prompt from the beginning
            prompt_lines = []
            param_started = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check if this line starts a parameter section
                if any(key in line.lower() for key in ['steps:', 'sampler:', 'cfg scale:', 'seed:', 'size:', 'model:']):
                    param_started = True
                    break
                    
                if not param_started and 'negative prompt:' not in line.lower():
                    prompt_lines.append(line)
            
            if prompt_lines:
                metadata['prompt'] = '\n'.join(prompt_lines).strip()
        
        # Now process line by line for parameters
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Check for Negative prompt section
            if line.lower().startswith('negative prompt:'):
                current_section = 'negative'
                metadata['negative_prompt'] = line[15:].strip()
                continue
            
            # If we're in negative prompt section, append to it
            if current_section == 'negative':
                if any(key in line.lower() for key in ['steps:', 'sampler:', 'cfg scale:', 'seed:', 'size:', 'model:']):
                    current_section = None
                else:
                    metadata['negative_prompt'] += ' ' + line
                    continue
            
            # Parse key-value pairs
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key, value = parts
                    key = key.strip().lower()
                    value = value.strip()
                    
                    # Handle specific parameters
                    if 'step' in key:
                        metadata['steps'] = value.split(',')[0].strip()
                    elif 'sampler' in key:
                        metadata['sampler'] = value.split(',')[0].strip()
                    elif 'schedule type' in key or 'schedule' in key:
                        metadata['schedule_type'] = value.split(',')[0].strip()
                    elif 'cfg scale' in key or 'cfg' in key:
                        metadata['cfg_scale'] = value.split(',')[0].strip()
                    elif 'distilled cfg scale' in key:
                        metadata['distilled_cfg_scale'] = value.split(',')[0].strip()
                    elif 'seed' in key:
                        metadata['seed'] = value.split(',')[0].strip()
                    elif 'size' in key:
                        metadata['size'] = value.split(',')[0].strip()
                    elif 'model hash' in key:
                        metadata['model_hash'] = value.split(',')[0].strip()
                    elif 'model' in key and 'hash' not in key and 'name' not in key:
                        model_value = value.split(',')[0].strip()
                        # Remove quotes if present
                        if model_value.startswith('"') and model_value.endswith('"'):
                            model_value = model_value[1:-1]
                        metadata['model'] = model_value
                        metadata['model_name'] = model_value
                    elif 'model name' in key:
                        model_name = value.split(',')[0].strip()
                        # Remove quotes if present
                        if model_name.startswith('"') and model_name.endswith('"'):
                            model_name = model_name[1:-1]
                        metadata['model_name'] = model_name
                        metadata['model'] = model_name
                    elif 'version' in key:
                        metadata['version'] = value.split(',')[0].strip()
                    elif 'clip skip' in key:
                        metadata['clip_skip'] = value.split(',')[0].strip()
                    elif 'module' in key:
                        # Store as additional parameter
                        metadata[f'module_{key.split()[1]}'] = value.strip()
        
        # Special case for the sketch example format
        if not metadata.get('prompt') and params_str and not any(key in params_str.lower() for key in ['steps:', 'sampler:', 'cfg scale:', 'seed:', 'size:', 'model:']):
            # If there's no parameters detected but there is text, treat the whole thing as a prompt
            metadata['prompt'] = params_str.strip()
        
        # If model is set but model_name is not, use model as model_name
        if metadata.get('model') and not metadata.get('model_name'):
            metadata['model_name'] = metadata['model']
        elif not metadata.get('model') and metadata.get('model_name'):
            metadata['model'] = metadata['model_name']
            
        # Add Stable Diffusion as a default tool if no tools are specified
        if not metadata.get('tools'):
            metadata['tools'] = ['Stable Diffusion']
    
    except Exception as e:
        print(f"Error parsing metadata: {e}")
        import traceback
        traceback.print_exc()
        
    return metadata

def load_metadata():
    """Load metadata from file, with error handling and backup"""
    try:
        if os.path.exists(app.config['METADATA_FILE']):
            with open(app.config['METADATA_FILE'], 'r') as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Convert old list format to dictionary
                        return {item['filename']: item for item in data if 'filename' in item}
                    return data
                except json.JSONDecodeError:
                    print("Corrupted metadata file, creating backup and starting fresh")
                    # Create backup of corrupted file
                    backup_file = f"{app.config['METADATA_FILE']}.bak"
                    try:
                        import shutil
                        shutil.copy2(app.config['METADATA_FILE'], backup_file)
                        print(f"Created backup at {backup_file}")
                    except Exception as e:
                        print(f"Failed to create backup: {e}")
                    return {}
    except Exception as e:
        print(f"Error loading metadata: {e}")
    return {}

def check_nsfw_content(image_path, text):
    """Check if image or text contains NSFW content using basic word filtering"""
    if not text:
        return False
        
    # Basic list of NSFW terms
    nsfw_terms = ['nsfw', 'explicit', 'adult', 'nude', 'naked']
    text_lower = text.lower()
    
    return any(term in text_lower for term in nsfw_terms)

@app.route('/')
def index():
    """Render the main page"""
    print("Current working directory:", os.getcwd())
    print("Template folder:", os.path.join(os.getcwd(), 'templates'))
    print("Template exists:", os.path.exists(os.path.join(os.getcwd(), 'templates', 'index.html')))
    
    metadata = load_metadata()
    # Get unique categories and models
    categories = set()
    models = set()
    for item in metadata.values():
        if item.get('category'):
            categories.add(item['category'])
        if item.get('model_name'):
            models.add(item['model_name'])
    
    return render_template('index.html', 
                         images=metadata,
                         categories=sorted(list(categories)),
                         models=sorted(list(models)))

@app.route('/images')
def get_images():
    """Get all images metadata"""
    try:
        metadata = load_metadata()
        return jsonify(list(metadata.values()))
    except Exception as e:
        print(f"Error getting metadata: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/extract_metadata', methods=['POST'])
def extract_metadata():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        # Save file temporarily
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_' + secure_filename(file.filename))
        file.save(temp_path)
        
        # Extract metadata
        metadata = extract_ai_metadata(temp_path)
        
        # Delete temp file
        os.remove(temp_path)
        
        return jsonify(metadata)
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Check required fields
    if not request.form.get('category'):
        return jsonify({'error': 'Category is required'}), 400
    
    if not request.form.getlist('tools'):
        return jsonify({'error': 'At least one tool must be selected'}), 400

    try:
        # Save the image
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Extract metadata from image first
        img_metadata = extract_ai_metadata(filepath)
        print("Extracted image metadata:", json.dumps(img_metadata, indent=2))

        # Check for NSFW content
        prompt_text = img_metadata.get('prompt', '') + ' ' + img_metadata.get('negative_prompt', '')
        is_nsfw = check_nsfw_content(filepath, prompt_text) or request.form.get('is_nsfw') == 'true'

        # Combine image metadata with form data, prioritizing image metadata
        metadata = {
            'filename': filename,
            'original_filename': file.filename,
            'upload_date': datetime.now().isoformat(),
            'category': request.form.get('category'),
            'tools': img_metadata.get('tools') or request.form.getlist('tools'),
            'prompt': img_metadata.get('prompt') or request.form.get('prompt', ''),
            'negative_prompt': img_metadata.get('negative_prompt') or request.form.get('negative_prompt', ''),
            'model_name': img_metadata.get('model_name') or img_metadata.get('model') or request.form.get('model_name', ''),
            'steps': img_metadata.get('steps') or request.form.get('steps', ''),
            'sampler': img_metadata.get('sampler') or request.form.get('sampler', ''),
            'cfg_scale': img_metadata.get('cfg_scale') or request.form.get('cfg_scale', ''),
            'seed': img_metadata.get('seed') or request.form.get('seed', ''),
            'size': img_metadata.get('size') or request.form.get('size', ''),
            'is_nsfw': is_nsfw
        }
        
        # Add additional metadata fields
        if img_metadata.get('schedule_type'):
            metadata['schedule_type'] = img_metadata.get('schedule_type')
        if img_metadata.get('distilled_cfg_scale'):
            metadata['distilled_cfg_scale'] = img_metadata.get('distilled_cfg_scale')
        if img_metadata.get('model_hash'):
            metadata['model_hash'] = img_metadata.get('model_hash')
        if img_metadata.get('version'):
            metadata['version'] = img_metadata.get('version')
        if img_metadata.get('clip_skip'):
            metadata['clip_skip'] = img_metadata.get('clip_skip')
        if img_metadata.get('module_1'):
            metadata['module_1'] = img_metadata.get('module_1')

        # Save to metadata file
        all_metadata = load_metadata()
        all_metadata[filename] = metadata
        save_metadata(all_metadata)

        return jsonify({
            'success': True,
            'filename': filename,
            'metadata': metadata,
            'is_nsfw': is_nsfw
        })

    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/models')
def get_models():
    """Get unique list of model names from uploaded images"""
    try:
        metadata = load_metadata()
        models = set()
        for item in metadata.values():
            if item.get('model_name'):
                models.add(item['model_name'])
            elif item.get('model'):  # Fallback to 'model' field
                models.add(item['model'])
        return jsonify(sorted(list(models)))
    except Exception as e:
        print(f"Error getting models: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search')
def search_images():
    """Search images by prompt, model, or category"""
    try:
        query = request.args.get('q', '').lower()
        category = request.args.get('category', '').lower()
        model = request.args.get('model', '').lower()
        tool = request.args.get('tool', '').lower()
        
        metadata = load_metadata()
        results = []
        
        for item in metadata.values():
            matches = True
            
            # Filter by search query
            if query:
                prompt = (item.get('prompt') or '').lower()
                if query not in prompt:
                    matches = False
            
            # Filter by category
            if category and category != 'all':
                item_category = (item.get('category') or '').lower()
                if category != item_category:
                    matches = False
            
            # Filter by model
            if model and model != 'all':
                item_model = (item.get('model_name') or item.get('model') or '').lower()
                if model != item_model:
                    matches = False
            
            # Filter by tool
            if tool:
                item_tools = [t.lower() for t in (item.get('tools') or [])]
                if tool not in item_tools:
                    matches = False
            
            if matches:
                results.append(item)
        
        # Sort by upload date, newest first
        results.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        return jsonify(results)
    except Exception as e:
        print(f"Error searching images: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_nsfw', methods=['POST'])
def update_nsfw():
    try:
        print("Received NSFW update request")
        data = request.json
        print(f"Request data: {data}")
        
        image_id = data.get('image_id')  # This will now be the filename
        is_nsfw = data.get('is_nsfw')
        
        print(f"Updating NSFW status - Image filename: {image_id}, New status: {is_nsfw}")
        
        metadata = load_metadata()
        print(f"Current metadata: {metadata}")
        
        if image_id in metadata:
            print(f"Found image {image_id} in metadata")
            metadata[image_id]['is_nsfw'] = is_nsfw
            save_metadata(metadata)
            print(f"Saved metadata for image {image_id}")
            return jsonify({'success': True, 'is_nsfw': is_nsfw})
            
        print(f"Image {image_id} not found in metadata")
        return jsonify({'success': False, 'error': 'Image not found'})
    except Exception as e:
        print(f"Error in update_nsfw: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def save_metadata(metadata):
    """Save metadata to JSON file"""
    try:
        print(f"Saving metadata to file: {app.config['METADATA_FILE']}")
        with open(app.config['METADATA_FILE'], 'w') as f:
            json.dump(metadata, f, indent=4)
        print("Metadata saved successfully")
    except Exception as e:
        print(f"Error saving metadata: {e}")
        raise

if __name__ == '__main__':
    app.run(debug=True)
