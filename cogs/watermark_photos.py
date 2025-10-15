# cogs/watermark.py
import io
import os
import re
from typing import Optional

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# Small helper to parse color inputs like "white", "#fff", "#ffffff", "255,255,255"
COLOR_NAME_MAP = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "blue": (0, 120, 255),
    "green": (0, 200, 0),
    "yellow": (255, 200, 0),
}

def parse_color(s: Optional[str], default=(255, 255, 255)):
    if not s:
        return default
    s = s.strip()
    # name
    if s.lower() in COLOR_NAME_MAP:
        return COLOR_NAME_MAP[s.lower()]
    # hex: #RRGGBB or RRGGBB or #RGB
    m = re.match(r"^#?([0-9a-fA-F]{6})$", s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    m2 = re.match(r"^#?([0-9a-fA-F]{3})$", s)
    if m2:
        h = m2.group(1)
        return tuple(int(h[i]*2, 16) for i in range(3))
    # comma separated
    try:
        parts = [int(p.strip()) for p in s.split(",")]
        if len(parts) == 3 and all(0 <= p <= 255 for p in parts):
            return tuple(parts)
    except Exception:
        pass
    return default

def _load_font(font_name: str, size: int):
    """
    Try to load a TrueType font at the requested size.
    Tries:
      - font_name (as provided)
      - font_name + ".ttf"
      - common system font locations (DejaVuSans, Arial)
    Falls back to ImageFont.load_default() ONLY if nothing else is found.
    """
    candidates = []

    # If user passed a path-like name, try that first
    if any(sep in font_name for sep in ("/", "\\")):
        candidates.append(font_name)

    # try with and without .ttf
    candidates.append(font_name)
    if not font_name.lower().endswith(".ttf"):
        candidates.append(f"{font_name}.ttf")

    # common system locations (Linux, Windows, macOS)
    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ])

    for path in candidates:
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
            # allow trying a font name that the system's font resolver can find
            return ImageFont.truetype(path, size)
        except Exception:
            continue

    # last-resort: try DejaVu by name (Pillow on many systems can find it)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        pass

    # final fallback: PIL default (bitmap) — keep but note it doesn't honor size well
    return ImageFont.load_default()

class Watermark(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="photowatermark",
        description="Add a customizable watermark to an uploaded image and return it (no files saved)."
    )
    @app_commands.describe(
        image="The image file to watermark (attach here).",
        text="Watermark text to draw.",
        position="Where to place the watermark (bottom_right/bottom_left/top_right/top_left/center).",
        font="Font filename (or family) available on the host (e.g. Arial).",
        size="Font size in points (default 36).",
        opacity="Opacity for the watermark: 0.0-1.0 (or 0-255).",
        color="Text color (name, hex #RRGGBB, or R,G,B)."
    )
    async def watermark(
        self,
        interaction: Interaction,
        image: discord.Attachment,
        text: str,
        position: Optional[str] = "bottom_right",
        font: Optional[str] = "DejaVuSans",
        size: Optional[int] = 100,
        opacity: Optional[float] = 0.45,
        color: Optional[str] = "white"
    ):
        await interaction.response.defer()

        # Validate & open attachment
        try:
            img_bytes = await image.read()
            base_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to read/open image: {e}", ephemeral=True)
            return

        # normalize params
        try:
            size = max(8, min(400, int(size or 36)))
        except Exception:
            size = 36

        # calculate opacity byte 0-255
        try:
            op = float(opacity)
            if op > 1.5:
                op_val = int(max(0, min(255, op)))
            elif op > 1.0:
                op_val = int(max(0, min(255, op * 255)))
            else:
                op_val = int(max(0, min(255, op * 255)))
        except Exception:
            op_val = int(0.45 * 255)

        rgb = parse_color(color, default=(255, 255, 255))

        # load font with fallback
        font_obj = _load_font(font, size)

        # helper to measure text size reliably across Pillow versions
        def measure_text(draw_obj: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont):
            """
            Robust text measurement across Pillow versions.
            Returns (width, height).
            """
            # prefer draw.textbbox
            try:
                bbox = draw_obj.textbbox((0, 0), text, font=fnt)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                pass

            # try font.getbbox
            try:
                bbox = fnt.getbbox(text)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                pass

            # fallback to getsize
            try:
                return fnt.getsize(text)
            except Exception:
                pass

            # last resort: approximate
            approx_w = len(text) * (getattr(fnt, "size", 12) // 2)
            approx_h = getattr(fnt, "size", 12)
            return approx_w, approx_h

        # ---------- updated watermark drawing block (inside your watermark method) ----------
        # (replace the existing overlay / shrink-to-fit section with this)
        try:
            # Load an initial font object using the requested size
            cur_size = max(8, min(400, int(size or 36)))
            cur_font = _load_font(font, cur_size)

            # Create an overlay for text so alpha compositing works cleanly
            overlay = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            # measure text using the helper
            tw, th = measure_text(draw, text, cur_font)

            # if cur_font is the PIL default bitmap (has no attribute 'getmetrics' or small size),
            # attempt to prefer a TrueType fallback. But still proceed.
            is_bitmap_fallback = (cur_font == ImageFont.load_default())

            # shrink-to-fit logic only if we have a TrueType-like font that can be resized
            max_width = int(base_img.width * 0.6)
            if tw > max_width and not is_bitmap_fallback:
                # reduce font size until it fits (guarded loop)
                while tw > max_width and cur_size > 8:
                    cur_size = max(8, int(cur_size * 0.9))
                    cur_font = _load_font(font, cur_size)
                    tw, th = measure_text(draw, text, cur_font)
                    # break if we reached a stable small font
                    if cur_size <= 8:
                        break

            # If after shrink the font is still too large and we are using bitmap fallback,
            # we can optionally split the text into multiple lines instead of shrinking further.
            if tw > max_width and is_bitmap_fallback:
                # naive wrap: break into words and join lines until width satisfied
                words = text.split()
                lines = []
                cur_line = ""
                for w in words:
                    test = (cur_line + " " + w).strip()
                    tw_test, _ = measure_text(draw, test, cur_font)
                    if tw_test <= max_width:
                        cur_line = test
                    else:
                        if cur_line:
                            lines.append(cur_line)
                        cur_line = w
                if cur_line:
                    lines.append(cur_line)
                text_to_draw = "\n".join(lines)
                # re-measure multi-line text by summing heights and taking max width
                max_tw = 0
                total_th = 0
                for ln in text_to_draw.split("\n"):
                    ln_w, ln_h = measure_text(draw, ln, cur_font)
                    max_tw = max(max_tw, ln_w)
                    total_th += ln_h
                tw, th = max_tw, total_th
            else:
                text_to_draw = text

            margin = max(8, int(base_img.width * 0.02))
            positions_map = {
                "bottom_right": (base_img.width - tw - margin, base_img.height - th - margin),
                "bottom_left": (margin, base_img.height - th - margin),
                "top_right": (base_img.width - tw - margin, margin),
                "top_left": (margin, margin),
                "center": ((base_img.width - tw) // 2, (base_img.height - th) // 2)
            }
            pos_key = (position or "bottom_right").lower()
            xy = positions_map.get(pos_key, positions_map["bottom_right"])

            # draw shadow + main text (support multi-line)
            shadow_color = (0, 0, 0, int(op_val * 0.9))
            fill_color = (rgb[0], rgb[1], rgb[2], op_val)

            # draw each line if multi-line
            y_offset = 0
            for ln in text_to_draw.split("\n"):
                ln_w, ln_h = measure_text(draw, ln, cur_font)
                x = xy[0]
                y = xy[1] + y_offset
                draw.text((x + 1, y + 1), ln, font=cur_font, fill=shadow_color)
                draw.text((x, y), ln, font=cur_font, fill=fill_color)
                y_offset += ln_h

            # composite and finalize
            result = Image.alpha_composite(base_img, overlay)
            buf = io.BytesIO()
            result.save(buf, format="PNG")
            buf.seek(0)
            discord_file = discord.File(fp=buf, filename="watermarked.png")
            await interaction.followup.send(content="✅ Here is your watermarked image (click to download):", file=discord_file)
            return

        except Exception as e:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)
            await interaction.followup.send(f"❌ Failed to compose/send watermarked image: {e}", ephemeral=True)
            return

async def setup(bot: commands.Bot):
    await bot.add_cog(Watermark(bot))
