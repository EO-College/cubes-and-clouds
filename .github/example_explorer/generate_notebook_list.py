import os
import json
import nbformat
import yaml
import subprocess
from urllib.parse import urlparse
import re
import base64
from PIL import Image
from io import BytesIO

ROOT_DIR = os.path.abspath(".")
OUTPUT_FILE = "notebooks.json"
NOTEBOOK_DIR = "lectures"
JHUB_INSTANCE = "workspace.earthcode.eox.at"
IGNORE_FOLDERS = [
    "venv",
    ".git",
    ".github",
    "_build",
    "dist",
    "9.9_master_asi_conae",
]
DEF_ORG = "EO-college"
DEF_REPO = "cubes-and-clouds"


def extract_last_image(
    nb,
    notebook_rel_path,
    output_dir="_build/html/build/_assets/previews",
    target_width=300,
):
    os.makedirs(output_dir, exist_ok=True)
    found_images = []
    # Check markdown cells for images
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            lines = cell.source.splitlines()
            for line in lines:
                # Match Markdown image: ![alt](path)
                md_img = re.findall(r"!\[.*?\]\((.*?)\)", line)
                if md_img:
                    found_images.extend(md_img)
                # Match MyST figure directive: :::{figure} ./image.png
                myst_img = re.findall(r":::\{figure\}\s+(.*?)\s*$", line)
                if myst_img:
                    found_images.extend(myst_img)

    if found_images:
        last_image_rel = found_images[-1].strip()
        notebook_dir = os.path.dirname(notebook_rel_path)
        image_abs_path = os.path.normpath(os.path.join(notebook_dir, last_image_rel))
        print(f"[info] Found image: {image_abs_path}")

        if os.path.exists(image_abs_path):
            try:
                with Image.open(image_abs_path) as img:
                    # Resize while preserving aspect ratio
                    w_percent = target_width / float(img.size[0])
                    h_size = int(float(img.size[1]) * w_percent)
                    img = img.resize((target_width, h_size), Image.LANCZOS)

                    # Save to unique file
                    image_name = notebook_rel_path.replace("/", "_").replace(
                        ".ipynb", "_preview.png"
                    )
                    output_path = os.path.join(output_dir, image_name)
                    img.save(output_path)
                    relpath = os.path.join("build/_assets/previews", image_name)
                    return os.path.relpath(relpath, start=".").replace("\\", "/")
            except Exception as e:
                print(
                    f"[warn] Couldn't load/resize MyST image for {notebook_rel_path}: {e}"
                )

    # If no markdown images, check code output
    for cell in reversed(nb.cells):
        if cell.cell_type == "code":
            for output in reversed(cell.get("outputs", [])):
                data = output.get("data", {})
                if "image/png" in data:
                    b64 = data["image/png"]
                    image_bytes = base64.b64decode(b64)

                    try:
                        # Load image from bytes
                        image = Image.open(BytesIO(image_bytes))
                        # Resize while maintaining aspect ratio
                        w_percent = target_width / float(image.size[0])
                        h_size = int(float(image.size[1]) * w_percent)
                        image = image.resize((target_width, h_size), Image.LANCZOS)

                        # Create a filename based on notebook path
                        base_name = notebook_rel_path.replace("/", "_").replace(
                            ".ipynb", "_preview.png"
                        )
                        image_path = os.path.join(output_dir, base_name)
                        image.save(image_path)
                        relpath = os.path.join("build/_assets/previews", base_name)

                        return os.path.relpath(relpath, start=".").replace("\\", "/")
                    except Exception as e:
                        print(
                            f"[warn] Failed to process image in {notebook_rel_path}: {e}"
                        )
                        return None
    return None


def parse_gitmodules():
    """Parse .gitmodules to map paths to remote info."""
    gitmodules_path = os.path.join(ROOT_DIR, ".gitmodules")
    if not os.path.exists(gitmodules_path):
        return {}

    submodules = {}
    current = {}

    with open(gitmodules_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[submodule"):
                if current:
                    submodules[current["path"]] = current["url"]
                current = {}
            elif "=" in line:
                key, value = [x.strip() for x in line.split("=", 1)]
                current[key] = value
        if current:
            submodules[current["path"]] = current["url"]

    # Convert to path → { org, repo }
    result = {}
    for path, url in submodules.items():
        if url.endswith(".git"):
            url = url[:-4]
        if url.startswith("git@"):
            url = url.replace(":", "/").replace("git@", "https://")
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            norm_path = os.path.normpath(path)
            result[norm_path] = {"org": parts[0], "repo": parts[1], "url": url}

    return result


def get_git_remote_info(repo_path):
    try:
        print(repo_path)
        url = subprocess.check_output(
            ["git", "-C", repo_path, "config", "--get", "remote.origin.url"], text=True
        ).strip()
        print(url)
        if url.endswith(".git"):
            url = url[:-4]
        if url.startswith("git@"):
            url = url.replace(":", "/").replace("git@", "https://")
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return {"org": parts[0], "repo": parts[1], "url": url}
    except Exception as e:
        print(f"[warn] Could not get git remote info from {repo_path}: {e}")
    return {"org": DEF_ORG, "repo": DEF_REPO, "url": url}


def extract_frontmatter(notebook_path):
    try:
        nb = nbformat.read(notebook_path, as_version=4)
        if nb.cells and nb.cells[0].cell_type == "markdown":
            content = nb.cells[0].source
            if content.strip().startswith("---"):
                block = content.split("---")[1]
                return yaml.safe_load(block)
    except Exception as e:
        print(f"[warn] Failed to extract frontmatter from {notebook_path}: {e}")
    return {}


def myst_url_sanitation(url):
    # reverse engineering the myst url sanitation
    clean_url = (
        url.replace("_-_", "-")
        .replace("_", "-")
        .replace(" ", "-")
        .replace(".", "")
        .replace(":", "")
        .replace("'", "")
        .replace('"', "")
        .lower()
    )
    parts = clean_url.split("/")
    cut_url = "/".join(parts[0:-1] + [parts[-1][:50]])
    # remove numbers
    url_without_numbers = "".join([i for i in cut_url if not i.isdigit()])
    back_to_parts = url_without_numbers.split("/")
    # remove trailing and leading dash - char
    sanitized_url_without_starting_ending_dash = "/".join(
        [j.strip("-") for j in back_to_parts]
    )
    return sanitized_url_without_starting_ending_dash


def extract_title_from_first_header(nb):
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            lines = cell.source.splitlines()
            for line in lines:
                match = re.match(r"^\s*#\s+(.*)", line)
                if match:
                    return match.group(1).strip()
    return None


def collect_notebooks():
    catalog = []
    git_url = get_git_remote_info(ROOT_DIR)["url"]

    # --- Local notebooks
    local_path = os.path.join(ROOT_DIR, NOTEBOOK_DIR)
    for dirpath, _, filenames in os.walk(local_path):
        if any(ignored in dirpath for ignored in IGNORE_FOLDERS):
            continue
        for file in filenames:
            if file.endswith(".ipynb"):
                abs_path = os.path.join(dirpath, file)
                rel_path = os.path.relpath(abs_path, ROOT_DIR).replace("\\", "/")
                meta = extract_frontmatter(abs_path)
                nb = nbformat.read(abs_path, as_version=4)
                image = meta.get("image") or extract_last_image(nb, rel_path)
                # TODO: need to extract available branch
                catalog.append(
                    {
                        "title": meta.get(
                            "title",
                            extract_title_from_first_header(nb)
                            or os.path.splitext(file)[0].replace("_", " "),
                        ),
                        "description": meta.get("description", ""),
                        "metadata": meta,
                        "image": image,
                        "link": myst_url_sanitation(rel_path.replace(".ipynb", "")),
                        "org": DEF_ORG,
                        "repo": DEF_REPO,
                        "source": "local",
                        "path": rel_path,
                        "gitpuller": f"https://{JHUB_INSTANCE}/hub/user-redirect/git-pull?repo={git_url}&urlpath=lab/tree/{DEF_REPO}/{rel_path}&branch=main",
                    }
                )

    return catalog


if __name__ == "__main__":
    notebooks = sorted(collect_notebooks(), key=lambda x: x["title"])
    with open(OUTPUT_FILE, "w") as f:
        json.dump(notebooks, f, indent=2)
    print(f"✅ Catalog saved to {OUTPUT_FILE} with {len(notebooks)} notebooks")
