from PIL import Image, ImageDraw, ImageFont
import os

# Create a simple payslip image
width, height = 800, 600
img = Image.new('RGB', (width, height), color='white')
draw = ImageDraw.Draw(img)

# Try to use a default font
try:
    font_title = ImageFont.truetype("arial.ttf", 36)
    font_large = ImageFont.truetype("arial.ttf", 28)
    font_normal = ImageFont.truetype("arial.ttf", 22)
except:
    font_title = ImageFont.load_default()
    font_large = ImageFont.load_default()
    font_normal = ImageFont.load_default()

# Draw payslip content
y_pos = 50
draw.text((width/2 - 150, y_pos), "PAYSLIP", fill='black', font=font_title)
y_pos += 80

draw.text((50, y_pos), "Employee Name: John Doe", fill='black', font=font_normal)
y_pos += 50

draw.text((50, y_pos), "Employee ID: EMP12345", fill='black', font=font_normal)
y_pos += 50

draw.text((50, y_pos), "Month: December 2025", fill='black', font=font_normal)
y_pos += 80

draw.rectangle([(50, y_pos), (750, y_pos + 2)], fill='black')
y_pos += 30

draw.text((50, y_pos), "Basic Salary:", fill='black', font=font_normal)
draw.text((400, y_pos), "Rs. 45,000", fill='black', font=font_normal)
y_pos += 40

draw.text((50, y_pos), "HRA:", fill='black', font=font_normal)
draw.text((400, y_pos), "Rs. 15,000", fill='black', font=font_normal)
y_pos += 40

draw.text((50, y_pos), "Allowances:", fill='black', font=font_normal)
draw.text((400, y_pos), "Rs. 10,000", fill='black', font=font_normal)
y_pos += 60

draw.rectangle([(50, y_pos), (750, y_pos + 2)], fill='black')
y_pos += 30

draw.text((50, y_pos), "GROSS SALARY:", fill='black', font=font_large)
draw.text((400, y_pos), "Rs. 70,000", fill='black', font=font_large)
y_pos += 60

draw.text((50, y_pos), "Deductions:", fill='black', font=font_normal)
draw.text((400, y_pos), "Rs. 5,000", fill='black', font=font_normal)
y_pos += 60

draw.rectangle([(50, y_pos), (750, y_pos + 3)], fill='black')
y_pos += 30

draw.text((50, y_pos), "NET SALARY:", fill='black', font=font_large)
draw.text((400, y_pos), "Rs. 65,000", fill='black', font=font_large)

# Save image
from pathlib import Path
output_dir = Path(__file__).parent / "frontend"
output_dir.mkdir(exist_ok=True)
output_path = output_dir / "sample_payslip.png"
img.save(output_path)
print(f"Sample payslip created at: {output_path}")
print("You can upload this file to test the OCR!")
