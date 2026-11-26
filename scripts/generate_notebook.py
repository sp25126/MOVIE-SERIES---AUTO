import json
from pathlib import Path

def create_colab_notebook():
    single_cell_code = [
        "#@title 🎬 Otaku AI Viral Shorts Studio — All-in-One Single Cell\n",
        "TOPIC_OVERRIDE = \"\" #@param {type:\"string\"}\n",
        "PILLAR_DAY_OVERRIDE = 0 #@param [0, 1, 2, 3, 4] {type:\"raw\"}\n",
        "USE_LOCAL_SMALL_MODEL = False #@param {type:\"boolean\"}\n",
        "DURATION_MODE = \"AI Decides Cut Duration (Full Climax)\" #@param [\"AI Decides Cut Duration (Full Climax)\", \"Full Uncut (Patrick Jane Style)\", \"Custom Seconds\"]\n",
        "CUSTOM_SECONDS = 18 #@param {type:\"integer\"}\n",
        "UPLOAD_TO_YOUTUBE = False #@param {type:\"boolean\"}\n",
        "GEMINI_API_KEY = \"\" #@param {type:\"string\"}\n",
        "\n",
        "import os, sys, subprocess, shutil, importlib, pathlib\n",
        "\n",
        "# 1. Quiet system & Python setup (no noisy apt r2u warnings)\n",
        "print(\"⚙️ [1/4] Preparing cloud environment...\")\n",
        "if not shutil.which(\"ffmpeg\"):\n",
        "    subprocess.run(\"apt-get update -qq 2>/dev/null && apt-get install -y -qq ffmpeg fonts-dejavu-core >/dev/null 2>&1\", shell=True)\n",
        "subprocess.run([\n",
        "    sys.executable, \"-m\", \"pip\", \"install\", \"-q\", \"--disable-pip-version-check\",\n",
        "    \"yt-dlp\", \"pillow\", \"opencv-python-headless\", \"google-generativeai\",\n",
        "    \"google-api-python-client\", \"google-auth-oauthlib\", \"transformers\", \"accelerate\"\n",
        "], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n",
        "\n",
        "# 2. Clone or pull latest studio repo\n",
        "if not os.path.exists(\"autonomous_pipeline.py\"):\n",
        "    if not os.path.exists(\"otaku_repo\"):\n",
        "        subprocess.run([\"git\", \"clone\", \"-q\", \"https://github.com/sp25126/MOVIE-SERIES---AUTO.git\", \"otaku_repo\"], check=True)\n",
        "    os.chdir(\"otaku_repo\")\n",
        "else:\n",
        "    subprocess.run([\"git\", \"pull\", \"-q\"], check=False)\n",
        "\n",
        "if os.getcwd() not in sys.path:\n",
        "    sys.path.insert(0, os.getcwd())\n",
        "\n",
        "# 3. Load secrets (Gemini API key & optional YouTube cookies)\n",
        "os.makedirs(\"config\", exist_ok=True)\n",
        "if not GEMINI_API_KEY:\n",
        "    try:\n",
        "        from google.colab import userdata\n",
        "        GEMINI_API_KEY = userdata.get(\"GEMINI_API_KEY\") or \"\"\n",
        "    except Exception:\n",
        "        pass\n",
        "if GEMINI_API_KEY:\n",
        "    os.environ[\"GEMINI_API_KEY\"] = GEMINI_API_KEY\n",
        "\n",
        "try:\n",
        "    from google.colab import userdata\n",
        "    _ck = userdata.get(\"YOUTUBE_COOKIES_TXT\")\n",
        "    if _ck:\n",
        "        open(\"config/cookies.txt\", \"w\").write(_ck)\n",
        "        print(\"✅ Loaded YouTube cookies from Colab Secrets.\")\n",
        "except Exception:\n",
        "    pass\n",
        "if not os.path.exists(\"config/cookies.txt\") and os.path.exists(\"/content/drive/MyDrive/cookies.txt\"):\n",
        "    shutil.copy(\"/content/drive/MyDrive/cookies.txt\", \"config/cookies.txt\")\n",
        "    print(\"✅ Loaded YouTube cookies from Google Drive.\")\n",
        "\n",
        "# 4. Reload modules & execute 8-step multi-platform pipeline (IG + TikTok + YouTube)\n",
        "import category_skills, clip_harvester, llm_director, dsp_renderer, metadata_uploader, autonomous_pipeline\n",
        "for _m in (category_skills, clip_harvester, llm_director, dsp_renderer, metadata_uploader, autonomous_pipeline):\n",
        "    importlib.reload(_m)\n",
        "\n",
        "CLIP_DURATION_SEC = 0.0 if (\"AI Decides\" in DURATION_MODE or \"Full Uncut\" in DURATION_MODE) else float(CUSTOM_SECONDS)\n",
        "print(f\"🚀 [2/4] Launching 8-step pipeline (IG + TikTok + YouTube)...\")\n",
        "\n",
        "result = autonomous_pipeline.run_autonomous_workflow(\n",
        "    day_override=int(PILLAR_DAY_OVERRIDE),\n",
        "    topic_override=TOPIC_OVERRIDE.strip(),\n",
        "    use_local_vlm=bool(USE_LOCAL_SMALL_MODEL),\n",
        "    upload=bool(UPLOAD_TO_YOUTUBE),\n",
        "    clip_dur=CLIP_DURATION_SEC,\n",
        ")\n",
        "\n",
        "out_video = pathlib.Path(result[\"output_mp4\"])\n",
        "meta = result[\"metadata\"]\n",
        "print(f\"\\n🎉 DONE! {out_video.name} ({out_video.stat().st_size / 1e6:.2f} MB)\")\n",
        "print(f\"Category: {result['category']} | Topic: {result['topic']}\")\n",
        "print(f\"Title:    {meta['title']}\")\n",
        "print(f\"Slot:     {meta['recommended_slot_utc']}\")\n",
        "print(f\"\\n--- DESCRIPTION ---\\n{meta['description']}\")\n",
        "\n",
        "from IPython.display import Video, display\n",
        "display(Video(str(out_video), embed=True, width=360))\n",
    ]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {
                "name": "Otaku AI Viral Shorts Studio (Single-Cell)",
                "provenance": [],
                "toc_visible": False
            },
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3"
            },
            "language_info": {
                "name": "python"
            }
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# 🎬 Otaku AI Viral Shorts Studio (Single-Cell Colab & Kaggle Edition)\n",
                    "Tap **Run (▶)** on the single cell below. It handles setup, multi-platform harvesting (**Instagram + TikTok + YouTube**), AI frame inspection & cut-point scoring, 1080×1920 DSP rendering, QA self-healing, SEO metadata, and inline preview."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {"cellView": "form"},
                "outputs": [],
                "source": single_cell_code
            }
        ]
    }

    out_file = Path("Otaku_Viral_Shorts_Studio.ipynb")
    out_file.write_text(json.dumps(nb, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {out_file} successfully ({out_file.stat().st_size} bytes, {len(nb['cells'])} cells)")

if __name__ == "__main__":
    create_colab_notebook()
