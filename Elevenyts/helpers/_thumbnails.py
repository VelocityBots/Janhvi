# PATCH FOR _thumbnails.py

# Replace the old watermark draw.text(...) block with:

watermark = _decode_f()

btn_x = 35
btn_y = 18
btn_w = 230
btn_h = 55

draw.rounded_rectangle(
    (btn_x-2, btn_y-2, btn_x+btn_w+2, btn_y+btn_h+2),
    radius=18,
    fill=(255, 0, 0, 60)
)

draw.rounded_rectangle(
    (btn_x, btn_y, btn_x+btn_w, btn_y+btn_h),
    radius=16,
    fill=(20, 20, 20, 210),
    outline=(255, 60, 60, 255),
    width=2
)

draw.text(
    (btn_x + 20, btn_y + 12),
    watermark,
    fill=(255, 255, 255),
    font=self.signature_font
)
