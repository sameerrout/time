import os
from PIL import Image, ImageDraw

def create_icons(output_dir="assets/icons"):
    os.makedirs(output_dir, exist_ok=True)
    
    # Common canvas: 128x128 with transparent background
    def new_canvas():
        return Image.new("RGBA", (128, 128), (0, 0, 0, 0))

    # 1. Barcode Scanner Icon (Modern scanner gun + red laser)
    img1 = new_canvas()
    d1 = ImageDraw.Draw(img1)
    # Circle background (soft blue tint #eff6ff, border #bfdbfe)
    d1.ellipse([4, 4, 124, 124], fill="#eff6ff", outline="#bfdbfe", width=3)
    # Scanner head
    d1.rounded_rectangle([36, 32, 92, 60], radius=8, fill="#1e293b")
    # Scanner barrel/window
    d1.rounded_rectangle([32, 38, 40, 54], radius=4, fill="#3b82f6")
    # Scanner handle
    d1.polygon([(52, 60), (76, 60), (68, 96), (48, 96)], fill="#334155")
    # Scanner base
    d1.rounded_rectangle([44, 94, 72, 104], radius=4, fill="#1e293b")
    # Red scan laser beams
    d1.line([(18, 46), (32, 46)], fill="#ef4444", width=3)
    d1.line([(16, 38), (30, 42)], fill="#ef4444", width=2)
    d1.line([(16, 54), (30, 50)], fill="#ef4444", width=2)
    img1.save(os.path.join(output_dir, "icon_scanner.png"), format="PNG")

    # 2. Barcode Generator Icon (Crisp barcode lines + QR tag)
    img2 = new_canvas()
    d2 = ImageDraw.Draw(img2)
    # Circle background (soft emerald tint #f0fdf4, border #bbf7d0)
    d2.ellipse([4, 4, 124, 124], fill="#f0fdf4", outline="#bbf7d0", width=3)
    # Label card
    d2.rounded_rectangle([28, 30, 100, 98], radius=8, fill="#ffffff", outline="#059669", width=3)
    # Barcode bars inside label
    bars = [
        (38, 4), (46, 2), (51, 6), (60, 3), (66, 7), (76, 2), (81, 5), (89, 3)
    ]
    for x, w in bars:
        d2.rectangle([x, 42, x + w, 76], fill="#0f172a")
    # Human readable text line below barcode
    d2.rounded_rectangle([38, 82, 90, 88], radius=2, fill="#059669")
    img2.save(os.path.join(output_dir, "icon_generator.png"), format="PNG")

    # 3. Stock Database Icon (Clean database disks / storage shelves)
    img3 = new_canvas()
    d3 = ImageDraw.Draw(img3)
    # Circle background (soft purple/indigo tint #f5f3ff, border #ddd6fe)
    d3.ellipse([4, 4, 124, 124], fill="#f5f3ff", outline="#ddd6fe", width=3)
    
    # Three stacked cylindrical database discs
    def draw_disc(y, fill_top, fill_body, outline):
        # Cylinder body
        d3.rectangle([34, y + 10, 94, y + 24], fill=fill_body, outline=outline, width=2)
        # Bottom curve
        d3.chord([34, y + 14, 94, y + 34], start=0, end=180, fill=fill_body, outline=outline, width=2)
        # Top cap
        d3.ellipse([34, y, 94, y + 20], fill=fill_top, outline=outline, width=2)

    # Bottom disc
    draw_disc(68, "#6366f1", "#4f46e5", "#4338ca")
    # Middle disc
    draw_disc(48, "#818cf8", "#6366f1", "#4f46e5")
    # Top disc
    draw_disc(28, "#a5b4fc", "#818cf8", "#6366f1")
    
    img3.save(os.path.join(output_dir, "icon_database.png"), format="PNG")
    print("Module icons generated successfully.")

if __name__ == "__main__":
    create_icons()
