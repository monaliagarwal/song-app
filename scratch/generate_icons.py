import os
import sys

def generate():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
        from PIL import Image, ImageDraw

    os.makedirs('static/icons', exist_ok=True)

    for size in [192, 512]:
        # Create a new image with #0a0a0a background
        img = Image.new('RGB', (size, size), color='#0a0a0a')
        draw = ImageDraw.Draw(img)
        
        # Color: #1DB954 (RGB: 29, 185, 84)
        green = (29, 185, 84)
        
        # Draw a stylish double music note (♫) using vectors for crispness
        # We define coordinates relative to size
        
        # Note heads (filled ellipses, rotated/tilted slightly)
        # Left head
        h1_x1 = int(size * 0.22)
        h1_y1 = int(size * 0.60)
        h1_x2 = int(size * 0.42)
        h1_y2 = int(size * 0.76)
        draw.ellipse([h1_x1, h1_y1, h1_x2, h1_y2], fill=green)
        
        # Right head
        h2_x1 = int(size * 0.58)
        h2_y1 = int(size * 0.50)
        h2_x2 = int(size * 0.78)
        h2_y2 = int(size * 0.66)
        draw.ellipse([h2_x1, h2_y1, h2_x2, h2_y2], fill=green)
        
        # Stems
        stem_width = max(2, int(size * 0.04))
        
        # Left stem
        s1_x1 = int(size * 0.38)
        s1_y1 = int(size * 0.25)
        s1_x2 = s1_x1 + stem_width
        s1_y2 = int(size * 0.68)
        draw.rectangle([s1_x1, s1_y1, s1_x2, s1_y2], fill=green)
        
        # Right stem
        s2_x1 = int(size * 0.74)
        s2_y1 = int(size * 0.15)
        s2_x2 = s2_x1 + stem_width
        s2_y2 = int(size * 0.58)
        draw.rectangle([s2_x1, s2_y1, s2_x2, s2_y2], fill=green)
        
        # Beam (polygon connecting the tops)
        beam_thickness = max(4, int(size * 0.09))
        p1 = (s1_x1, s1_y1)
        p2 = (s2_x2, s2_y1)
        p3 = (s2_x2, s2_y1 + beam_thickness)
        p4 = (s1_x1, s1_y1 + beam_thickness)
        draw.polygon([p1, p2, p3, p4], fill=green)
        
        # Save the image
        output_path = f'static/icons/icon-{size}.png'
        img.save(output_path, 'PNG')
        print(f"Saved icon: {output_path} ({size}x{size})")

if __name__ == '__main__':
    generate()
