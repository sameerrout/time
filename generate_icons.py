import os
from PIL import Image, ImageDraw

def create_app_icon(output_dir="assets/icons"):
    os.makedirs(output_dir, exist_ok=True)
    
    # 256x256 master image
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background rounded rectangle (Factory Industrial Dark Slate #1e293b)
    margin = 12
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=48,
        fill="#1e293b",
        outline="#3b82f6",
        width=6
    )
    
    # Stylized Issue Slip Sheet (White/Off-white paper #f8fafc)
    sheet_left = 52
    sheet_top = 46
    sheet_right = 204
    sheet_bottom = 214
    draw.rounded_rectangle(
        [sheet_left, sheet_top, sheet_right, sheet_bottom],
        radius=16,
        fill="#f8fafc",
        outline="#94a3b8",
        width=3
    )
    
    # Slip Header banner (#2563eb)
    draw.rounded_rectangle(
        [sheet_left + 14, sheet_top + 16, sheet_right - 14, sheet_top + 42],
        radius=6,
        fill="#2563eb"
    )
    
    # Stylized Barcode lines inside slip
    barcode_top = 100
    barcode_height = 42
    bar_patterns = [
        (68, 6), (78, 3), (85, 8), (97, 4), (105, 10),
        (120, 4), (128, 7), (139, 3), (146, 9), (160, 5),
        (170, 7), (181, 4)
    ]
    for x, w in bar_patterns:
        draw.rectangle([x, barcode_top, x + w, barcode_top + barcode_height], fill="#0f172a")
        
    # Document text lines below barcode
    draw.rounded_rectangle([68, 156, 188, 162], radius=3, fill="#64748b")
    draw.rounded_rectangle([68, 172, 160, 178], radius=3, fill="#94a3b8")
    draw.rounded_rectangle([68, 188, 130, 194], radius=3, fill="#cbd5e1")
    
    # Checkmark badge at bottom-right corner (#10b981 emerald)
    badge_cx, badge_cy, badge_r = 192, 192, 28
    draw.ellipse(
        [badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r],
        fill="#10b981",
        outline="#ffffff",
        width=4
    )
    
    # Checkmark in badge
    draw.line([(180, 192), (189, 201), (204, 183)], fill="#ffffff", width=5, joint="curve")
    
    # Save PNG
    png_path = os.path.join(output_dir, "app_icon.png")
    img.save(png_path, format="PNG")
    print(f"Generated PNG: {png_path}")
    
    # Save ICO with multiple resolutions (16, 32, 48, 64, 128, 256)
    ico_path = os.path.join(output_dir, "app_icon.ico")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Generated ICO: {ico_path}")

if __name__ == "__main__":
    create_app_icon()
