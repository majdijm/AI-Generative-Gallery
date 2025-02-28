from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import re
from PIL import Image

app = Flask(__name__)

# Configure upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['METADATA_FILE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.json')

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize profanity checking
HAS_PROFANITY = False
try:
    from better_profanity import profanity
    profanity.load_censor_words()
    HAS_PROFANITY = True
except ImportError:
    pass

def extract_ai_metadata(image_path):
    """Extract metadata from AI-generated images"""
    try:
        print(f"\nExtracting metadata from: {image_path}")
        metadata = {}
        
        with Image.open(image_path) as img:
            # Get image size
            width, height = img.size
            metadata['size'] = f"{width}x{height}"
            
            # Try to get PNG text chunks
            if 'parameters' in img.info:
                print("Found parameters in PNG chunks")
                params = img.info['parameters']
                # Parse the parameters
                parsed = parse_metadata_string(params)
                # Update metadata with parsed values
                for key, value in parsed.items():
                    if value:  # Only update if value is not empty
                        metadata[key] = value
            
            # Try to get EXIF data if we don't have complete metadata
            if not metadata.get('prompt') and hasattr(img, '_getexif') and img._getexif() is not None:
                print("Found EXIF data")
                exif = img._getexif()
                if 37510 in exif:  # UserComment tag
                    try:
                        exif_data = exif[37510].decode('utf8')
                        parsed = parse_metadata_string(exif_data)
                        # Update metadata with parsed values
                        for key, value in parsed.items():
                            if value and key not in metadata:  # Only update if value is not empty and key doesn't exist
                                metadata[key] = value
                    except:
                        pass
            
            # Try to get Fooocus metadata if we still don't have complete metadata
            if 'fooocus_v2' in img.info:
                print("Found Fooocus metadata")
                try:
                    fooocus_data = json.loads(img.info['fooocus_v2'])
                    if 'prompt' in fooocus_data and not metadata.get('prompt'):
                        metadata['prompt'] = fooocus_data['prompt']
                    if 'negative' in fooocus_data and not metadata.get('negative_prompt'):
                        metadata['negative_prompt'] = fooocus_data['negative']
                    if 'seed' in fooocus_data and not metadata.get('seed'):
                        metadata['seed'] = str(fooocus_data['seed'])
                except:
                    pass
        
        print("Extracted metadata:", json.dumps(metadata, indent=2))
        return metadata
        
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        import traceback
        traceback.print_exc()
        return {}

def parse_metadata_string(params_str):
    """Parse metadata string into structured format"""
    metadata = {
        'prompt': '',
        'negative_prompt': '',
        'steps': '',
        'sampler': '',
        'cfg_scale': '',
        'seed': '',
        'size': '',
        'model': '',
        'model_name': ''
    }
    
    try:
        # Try to parse as JSON first
        try:
            json_data = json.loads(params_str)
            if isinstance(json_data, dict):
                if 'prompt' in json_data:
                    metadata['prompt'] = json_data['prompt']
                if 'negative' in json_data:
                    metadata['negative_prompt'] = json_data['negative']
                if 'seed' in json_data:
                    metadata['seed'] = str(json_data['seed'])
                return metadata
        except json.JSONDecodeError:
            pass

        # If not JSON, parse as string
        lines = params_str.split('\n')
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
                if ':' in line:  # New section started
                    current_section = None
                else:
                    metadata['negative_prompt'] += ' ' + line
                    continue
            
            # If no negative prompt found yet, this must be the positive prompt
            if not metadata['prompt'] and not ':' in line:
                metadata['prompt'] = line
                continue
            
            # Parse key-value pairs
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'step' in key:
                    metadata['steps'] = value.split(',')[0].strip()
                elif 'sampler' in key:
                    metadata['sampler'] = value.split(',')[0].strip()
                elif 'cfg' in key:
                    metadata['cfg_scale'] = value.split(',')[0].strip()
                elif 'seed' in key:
                    metadata['seed'] = value.split(',')[0].strip()
                elif 'size' in key:
                    metadata['size'] = value.split(',')[0].strip()
                elif 'model' in key and 'hash' not in key:
                    metadata['model'] = value.split(',')[0].strip()
                    metadata['model_name'] = value.split(',')[0].strip()
                elif 'prompt' in key and not metadata['prompt']:
                    metadata['prompt'] = value
    
    except Exception as e:
        print(f"Error parsing metadata: {e}")
        
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
    """Check if image or text contains NSFW content"""
    if text:
        if HAS_PROFANITY:
            return profanity.contains_profanity(text)
        else:
            # Simple fallback profanity check
            basic_profanity = ['nsfw', 'explicit', 'adult']
            return any(word in text.lower() for word in basic_profanity)
    return False

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

        # Check for NSFW content
        prompt_text = request.form.get('prompt', '') + ' ' + request.form.get('negative_prompt', '')
        is_nsfw = check_nsfw_content(filepath, prompt_text)

        # Extract metadata from image
        img_metadata = extract_ai_metadata(filepath)

        # Combine form data with image metadata
        metadata = {
            'filename': filename,
            'original_filename': file.filename,
            'upload_date': datetime.now().isoformat(),
            'category': request.form.get('category'),
            'tools': request.form.getlist('tools'),
            'prompt': request.form.get('prompt') or img_metadata.get('prompt', ''),
            'negative_prompt': request.form.get('negative_prompt') or img_metadata.get('negative_prompt', ''),
            'model_name': request.form.get('model_name') or img_metadata.get('model', ''),
            'steps': request.form.get('steps') or img_metadata.get('steps', ''),
            'sampler': request.form.get('sampler') or img_metadata.get('sampler', ''),
            'cfg_scale': request.form.get('cfg_scale') or img_metadata.get('cfg_scale', ''),
            'seed': request.form.get('seed') or img_metadata.get('seed', ''),
            'size': request.form.get('size') or img_metadata.get('size', ''),
            'is_nsfw': is_nsfw
        }

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
