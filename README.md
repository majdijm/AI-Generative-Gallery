# AI Generative Gallery - v1

A modern web application for managing and displaying AI-generated images with advanced features for metadata extraction and NSFW content management.

Developed by AIVirtus - Majdi El-Jazmawi

## Features

- 🖼️ Clean, responsive image gallery interface
- 🔍 Automatic metadata extraction from AI-generated images
- 🏷️ Support for multiple AI model outputs (Stable Diffusion, Fooocus, etc.)
- 🔒 NSFW content management with blur effects
- 🏷️ Image categorization and filtering
- 🔍 Search functionality for prompts and metadata
- 📱 Mobile-friendly design

## Requirements

- Python 3.8 or higher
- Flask web framework
- TensorFlow (for image processing)
- Pillow (for image handling)
- SQLAlchemy (for future database integration)
- Better Profanity (for content filtering)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AIGG.git
   cd AIGG
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Windows:
     ```bash
     venv\Scripts\activate
     ```
   - Linux/Mac:
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Directory Structure

```
AIGG/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── templates/         
│   └── index.html     # Main gallery template
├── uploads/           # Image storage directory
└── metadata.json      # Image metadata storage
```

## Configuration

The application uses the following configuration:
- Images are stored in the `uploads/` directory
- Metadata is stored in `metadata.json`
- The application runs on `http://localhost:5000` by default

## Usage

1. Start the application:
   ```bash
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

3. Features:
   - Upload images using the "Upload Image" button
   - View image details by clicking on any image
   - Toggle NSFW status in image details
   - Filter images by category or model
   - Search through image prompts

## Image Metadata

The application automatically extracts metadata from AI-generated images, including:
- Prompts
- Negative prompts
- Model information
- Generation parameters (steps, CFG scale, seed)
- Image size
- NSFW status

Supported metadata formats:
- PNG text chunks
- EXIF data
- Fooocus metadata
- Standard image metadata

## Data Storage

- **Images**: Stored in the `uploads/` directory
- **Metadata**: Stored in `metadata.json`
  - Automatic backup created as `metadata.json.bak`
  - JSON format for easy editing and portability

## Security Features

- Secure filename handling
- Content type verification
- NSFW content management
- Backup system for metadata

## Browser Compatibility

Tested and working on:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Copyright

 2025 AIVirtus - Majdi El-Jazmawi. All rights reserved.
Version 1.0.0

## Acknowledgments

- Built with Flask
- UI powered by TailwindCSS
- Image processing by TensorFlow and Pillow
- Developed by AIVirtus - Majdi El-Jazmawi
