# cogs/video_watermark.py
import asyncio
import io
import os
import sys
import tempfile
from typing import Optional, Tuple
import discord
from discord import app_commands, Interaction
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# ---------- helpers ----------
def parse_color(color: Optional[str]) -> Tuple[int, int, int]:
    """Accept 'white', '#fff', '#ffffff', or 'r,g,b' and return (r,g,b)."""
    if not color:
        return (255, 255, 255)
    s = color.strip()
    names = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (255, 0, 0),
        "blue": (0, 120, 255),
        "green": (0, 200, 0),
    }
    if s.lower() in names:
        return names[s.lower()]
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        r = int(s[0]*2, 16); g = int(s[1]*2, 16); b = int(s[2]*2, 16)
        return (r, g, b)
    if len(s) == 6:
        r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
        return (r, g, b)
    # csv
    if "," in s:
        try:
            parts = [int(p.strip()) for p in s.split(",")]
            if len(parts) == 3:
                return (max(0, min(255, parts[0])),
                        max(0, min(255, parts[1])),
                        max(0, min(255, parts[2])))
        except Exception:
            pass
    return (255, 255, 255)

def parse_opacity(op: float) -> int:
    """Normalize opacity given as 0.0-1.0 (or 0-255) to 0-255 int."""
    try:
        v = float(op)
        if v <= 1.5:
            return int(max(0, min(255, round(v * 255))))
        else:
            return int(max(0, min(255, round(v))))
    except Exception:
        return int(0.45 * 255)

def _load_font(font_name: Optional[str], size: int) -> Tuple[ImageFont.FreeTypeFont, Optional[str]]:
    """
    Try to load a TrueType font at the requested size.
    Returns (font_object, font_path_used_or_None).
    Tries (in order):
      - If font_name looks like a path, try that exact path.
      - font_name (as given) and font_name + '.ttf'
      - common system font paths
      - a bare 'DejaVuSans.ttf' attempt
    Falls back to ImageFont.load_default() and returns (font, None).
    """
    candidates = []

    # If the caller provided None or empty, we'll still try system locations below
    if font_name:
        # If path-like, try that exact path first
        if any(sep in font_name for sep in ("/", "\\")) and os.path.exists(font_name):
            try:
                return ImageFont.truetype(font_name, size), font_name
            except Exception:
                # continue to other candidates
                pass

        # try the raw name and the .ttf variant (may be absolute or relative)
        candidates.append(font_name)
        if not font_name.lower().endswith(".ttf"):
            candidates.append(f"{font_name}.ttf")
        # also try a project-local fonts folder
        candidates.append(os.path.join(os.path.dirname(__file__), "fonts", f"{font_name}.ttf"))
        candidates.append(os.path.join(os.path.dirname(__file__), "fonts", font_name))

    # common known font paths
    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        # project-local fallback (relative)
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "Arial.ttf"),
    ])

    # Try each candidate carefully
    for path in candidates:
        if not path:
            continue
        # if path exists on disk, try that
        try:
            if os.path.isabs(path) and os.path.exists(path):
                f = ImageFont.truetype(path, size)
                return f, path
            # try relative-to-project path
            rel = os.path.join(os.path.dirname(__file__), path) if not os.path.isabs(path) else path
            if os.path.exists(rel):
                f = ImageFont.truetype(rel, size)
                return f, rel
            # last-ditch: try letting Pillow resolve the name (may work on some systems)
            try:
                f = ImageFont.truetype(path, size)
                return f, path
            except Exception:
                pass
        except Exception:
            # ignore and try next candidate
            continue

    # attempt bare DejaVu name as a final try
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", size)
        return f, "DejaVuSans.ttf"
    except Exception:
        pass

    # fallback to the tiny bitmap default (doesn't honor size)
    return ImageFont.load_default(), None

def make_watermark_png(
    text: str,
    fontsize: int,
    opacity_byte: int,
    color_rgb: Tuple[int,int,int],
    target_width: Optional[int] = None,
    font_name: Optional[str] = "DejaVuSans",
    debug: bool = False,
    force_font_size: bool = False
) -> Tuple[bytes, Optional[str], int, Tuple[int,int]]:
    """
    Render watermark text to a transparent PNG and return:
      (png_bytes, font_path_used_or_None, chosen_font_size, (img_w,img_h))

    - If target_width is provided and force_font_size is False: we'll search for a font size
      that produces width approx equal to target_width. The search has a large upper bound so
      it can select big sizes.
    - If force_font_size=True: we use `fontsize` exactly (no fitting / no scaling).
    - debug True just keeps returning the font_path; function always returns useful data.
    """
    # helper to measure
    def _measure(text: str, font: ImageFont.FreeTypeFont):
        dummy = Image.new("RGBA", (10, 10), (255,255,255,0))
        draw = ImageDraw.Draw(dummy)
        try:
            bbox = draw.textbbox((0,0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except Exception:
            w, h = draw.textsize(text, font=font)
        return int(w), int(h)

    # If we must force a specific size -> simple path
    if force_font_size or target_width is None:
        font, font_path = _load_font(font_name, fontsize)
        tw, th = _measure(text, font)
        pad = max(8, int(fontsize // 3))
        canvas_w = max(1, tw + pad*2)
        canvas_h = max(1, th + pad*2)
        img = Image.new("RGBA", (canvas_w, canvas_h), (255,255,255,0))
        draw = ImageDraw.Draw(img)
        shadow = (0, 0, 0, max(10, int(opacity_byte * 0.8)))
        text_color = (color_rgb[0], color_rgb[1], color_rgb[2], opacity_byte)
        draw.text((pad+1, pad+1), text, font=font, fill=shadow)
        draw.text((pad, pad), text, font=font, fill=text_color)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        chosen_size = fontsize
        if debug:
            return bio.read(), font_path, chosen_size, (canvas_w, canvas_h)
        return bio.read(), font_path, chosen_size, (canvas_w, canvas_h)

    # --- target_width fitting path ---
    # Robust search bounds: allow font size to grow well beyond requested fontsize.
    lo = 24
    hi = max(int(fontsize * 4), int(target_width * 2), 128)  # allow big fonts if needed
    best = None
    best_font_path = None
    best_size = None
    best_img = None
    best_diff = float("inf")

    # iterative search: try a range of sizes (not too many iterations)
    for candidate_size in [max(lo, int(x)) for x in (
            lo,
            (lo+hi)//2,
            hi,
            int(fontsize),
            int(fontsize*1.5),
            int(target_width//4),
            int(target_width//2),
            int(target_width)
        )]:
        if candidate_size < 6:
            continue
        try:
            font_cand, font_path_cand = _load_font(font_name, candidate_size)
            w_c, h_c = _measure(text, font_cand)
            pad = max(8, int(candidate_size // 3))
            total_w = w_c + pad*2
            diff = abs(total_w - target_width)
            if diff < best_diff:
                best_diff = diff
                best = font_cand
                best_font_path = font_path_cand
                best_size = candidate_size
                # build preview image
                canvas_w = max(1, int(total_w))
                canvas_h = max(1, int(h_c + pad*2))
                img_candidate = Image.new("RGBA", (canvas_w, canvas_h), (255,255,255,0))
                draw_c = ImageDraw.Draw(img_candidate)
                shadow = (0, 0, 0, max(10, int(opacity_byte * 0.8)))
                text_color = (color_rgb[0], color_rgb[1], color_rgb[2], opacity_byte)
                draw_c.text((pad+1, pad+1), text, font=font_cand, fill=shadow)
                draw_c.text((pad, pad), text, font=font_cand, fill=text_color)
                best_img = img_candidate
        except Exception:
            continue

    # if we didn't converge above, do binary-like search between lo and hi
    if best_img is None:
        lo = 8
        hi = max(int(fontsize * 4), int(target_width * 2), 256)
        for _ in range(30):
            mid = (lo + hi) // 2
            if mid < 6:
                lo = mid + 1
                continue
            try:
                font_cand, font_path_cand = _load_font(font_name, mid)
                w_c, h_c = _measure(text, font_cand)
            except Exception:
                hi = mid - 1
                continue
            pad = max(8, int(mid // 3))
            total_w = w_c + pad*2
            diff = total_w - target_width
            absdiff = abs(diff)
            if absdiff < best_diff:
                best_diff = absdiff
                best = font_cand
                best_font_path = font_path_cand
                best_size = mid
                canvas_w = max(1, int(total_w))
                canvas_h = max(1, int(h_c + pad*2))
                img_candidate = Image.new("RGBA", (canvas_w, canvas_h), (255,255,255,0))
                draw_c = ImageDraw.Draw(img_candidate)
                shadow = (0, 0, 0, max(10, int(opacity_byte * 0.8)))
                text_color = (color_rgb[0], color_rgb[1], color_rgb[2], opacity_byte)
                draw_c.text((pad+1, pad+1), text, font=font_cand, fill=shadow)
                draw_c.text((pad, pad), text, font=font_cand, fill=text_color)
                best_img = img_candidate
            # narrow search
            if diff > 0:
                hi = mid - 1
            else:
                lo = mid + 1

    if best_img is None:
        # final fallback: use fontsize
        font, font_path = _load_font(font_name, fontsize)
        tw, th = _measure(text, font)
        pad = max(8, int(fontsize // 3))
        canvas_w = max(1, tw + pad*2)
        canvas_h = max(1, th + pad*2)
        img = Image.new("RGBA", (canvas_w, canvas_h), (255,255,255,0))
        draw = ImageDraw.Draw(img)
        shadow = (0, 0, 0, max(10, int(opacity_byte * 0.8)))
        text_color = (color_rgb[0], color_rgb[1], color_rgb[2], opacity_byte)
        draw.text((pad+1, pad+1), text, font=font, fill=shadow)
        draw.text((pad, pad), text, font=font, fill=text_color)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        chosen_size = fontsize
        if debug:
            return bio.read(), font_path, chosen_size, (canvas_w, canvas_h)
        return bio.read(), font_path, chosen_size, (canvas_w, canvas_h)

    # best_img is ready
    bio = io.BytesIO()
    best_img.save(bio, format="PNG")
    bio.seek(0)
    chosen_size = best_size or fontsize
    if debug:
        return bio.read(), best_font_path, chosen_size, best_img.size
    return bio.read(), best_font_path, chosen_size, best_img.size

async def ffprobe_dimensions(path: str) -> Tuple[int,int]:
    """Return (width,height) using ffprobe; raise on failure."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(err.decode().strip() or "ffprobe error")
    s = out.decode().strip()
    if "x" in s:
        w, h = s.split("x")
        return int(w), int(h)
    raise RuntimeError("Failed to parse ffprobe output")

# ---------- Cog ----------
class VideoWatermark(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="videowatermark",
        description="Add a text watermark to an uploaded video (ffmpeg required)."
    )
    @app_commands.describe(
        video="Video file to watermark (attach)",
        text="Watermark text",
        position="Position: bottom_right, bottom_left, top_right, top_left, center",
        fontsize="Base font size (px)",
        opacity="Opacity 0.0-1.0 (or 0-255)",
        color="Text color (name, #RRGGBB, or R,G,B)",
        scale="Watermark width as fraction of video width (0.05 - 0.5). Default 0.2",
        fade_seconds="Optional fade in/out duration in seconds (0 = no fade)"
    )
    async def videowatermark(
        self,
        interaction: Interaction,
        video: discord.Attachment,
        text: str,
        position: str = "bottom_right",
        fontsize: int = 100,
        opacity: float = 0.45,
        color: str = "white",
        scale: float = 0.20,
        fade_seconds: float = 0.0
    ):
        """
        Example:
          /videowatermark video:<attach> text:"My watermark" position:bottom_right fontsize:48 opacity:0.5 color:#fff scale:0.2 fade_seconds:1.5
        """
        await interaction.response.defer(thinking=True)

        # Validate attachment
        if not video:
            return await interaction.followup.send("Please attach a video in the `video` option.", ephemeral=True)

        # Save attachment to temp file
        tmp_video = None
        tmp_wm = None
        tmp_out = None
        try:
            # write video to temp file
            tmp_video = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(video.filename)[1] or ".mp4")
            vbytes = await video.read()
            tmp_video.write(vbytes)
            tmp_video.flush()
            tmp_video.close()
            input_path = tmp_video.name

            # check ffmpeg availability
            try:
                proc = await asyncio.create_subprocess_exec("ffmpeg", "-version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()
            except FileNotFoundError:
                return await interaction.followup.send("FFmpeg/ffprobe not found on the host. Install ffmpeg to use this command.", ephemeral=True)

            # probe dimensions (fallback to default if fails)
            try:
                width, height = await ffprobe_dimensions(input_path)
            except Exception:
                width, height = 1280, 720

            # clamp scale
            try:
                scale = float(scale)
            except Exception:
                scale = 0.20
            scale = max(0.05, min(0.50, scale))

            # compute target watermark width in pixels
            target_w = max(20, int(width * scale))

            # prepare watermark png (scaled to target_w)
            rgb = parse_color(color)
            op_byte = parse_opacity(opacity)
            png_bytes, font_used, chosen_size, (img_w, img_h) = make_watermark_png(
                text,
                int(72),
                op_byte,
                rgb,
                target_width=None,
                font_name="DejaVuSans",
                debug=True,
                force_font_size=False
            )
            print(f"font_used={font_used}, chosen_size={chosen_size}, img={img_w}x{img_h}, target_w={target_w}")
            
            # write watermark to temp file
            tmp_wm = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_wm.write(png_bytes)
            tmp_wm.flush()
            tmp_wm.close()
            wm_path = tmp_wm.name

            # determine overlay expression
            pos = (position or "bottom_right").lower()
            if pos == "bottom_right":
                overlay_expr = "main_w-overlay_w-10:main_h-overlay_h-10"
            elif pos == "bottom_left":
                overlay_expr = "10:main_h-overlay_h-10"
            elif pos == "top_right":
                overlay_expr = "main_w-overlay_w-10:10"
            elif pos == "top_left":
                overlay_expr = "10:10"
            elif pos == "center":
                overlay_expr = "(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            else:
                overlay_expr = "main_w-overlay_w-10:main_h-overlay_h-10"

            # If fade_seconds > 0, build filter to fade the overlay in/out.
            # We'll use overlay with alphaenable: format=auto, then apply fade on the overlay stream.
            filters = []
            overlay_input_idx = 1  # watermark is second input
            if fade_seconds and fade_seconds > 0:
                # We apply fade on the overlay stream using fade t=in/out on alpha
                # Create filter_complex: [1]format=rgba,fade=type=in:st=0:d=fade_seconds:alpha=1[wm];[0][wm]overlay=...
                # We'll handle filter_complex in ffmpeg_cmd below
                filter_complex = f"[1]format=rgba,fade=t=in:st=0:d={fade_seconds}:alpha=1,fade=t=out:st=0:d={fade_seconds}:alpha=1[wm];[0][wm]overlay={overlay_expr}"
            else:
                filter_complex = f"[0][1]overlay={overlay_expr}"

            # Prepare output temp file
            tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            out_path = tmp_out.name
            tmp_out.close()

            # Build ffmpeg command. Keep audio if present.
            # Use libx264 with veryfast preset; feel free to adjust CRF/preset for quality/size tradeoff.
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path, "-i", wm_path,
                "-filter_complex", filter_complex,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy", "-movflags", "+faststart", out_path
            ]

            proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode(errors="ignore")[:2000]
                return await interaction.followup.send(f"FFmpeg failed to process the video. Stderr (truncated):\n```\n{err_text}\n```", ephemeral=True)

            # Check file size against Discord upload limits (default 8MB)
            # If your bot has larger upload capability, you can adjust this value accordingly.
            max_size = 50 * 1024 * 1024  # 50 MB
            final_size = os.path.getsize(out_path)
            if final_size > max_size:
                # Option: try to recompress more aggressively here. For now, return helpful message.
                return await interaction.followup.send(
                    f"Watermarked video is {final_size/1024/1024:.2f} MB which exceeds the upload limit ({max_size/1024/1024:.1f} MB). "
                    "Try a shorter clip or a lower resolution, or host the result externally.",
                    ephemeral=True
                )

            # Send the result back
            with open(out_path, "rb") as f:
                discord_file = discord.File(f, filename=f"watermarked_{os.path.basename(video.filename)}")
                await interaction.followup.send(content="✅ Here is your watermarked video (click to download):", file=discord_file)
            return

        except Exception as e:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)
            await interaction.followup.send(f"❌ Failed to watermark the video: {e}", ephemeral=True)
            return
        finally:
            # cleanup temp files
            for tmp in (tmp_video, tmp_wm, tmp_out):
                try:
                    if tmp:
                        os.unlink(tmp.name)
                except Exception:
                    pass

# setup
async def setup(bot: commands.Bot):
    await bot.add_cog(VideoWatermark(bot))
