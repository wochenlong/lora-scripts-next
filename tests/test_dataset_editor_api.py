import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app


ROOT = Path(__file__).resolve().parents[1]


def make_image(path: Path, color=(220, 80, 80)):
    image = Image.new("RGB", (24, 18), color)
    image.save(path)


def test_dataset_editor_scan_lists_images_and_captions(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("1girl, solo", encoding="utf-8")
    make_image(tmp_path / "beta.jpg", color=(80, 120, 220))

    client = TestClient(app)
    response = client.post("/api/dataset-editor/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["root"] == str(tmp_path.resolve()).replace("\\", "/")
    assert payload["data"]["total"] == 2
    assert payload["data"]["tags"] == [{"tag": "1girl", "count": 1}, {"tag": "solo", "count": 1}]
    assert payload["data"]["categories"] == [{"name": "根目录", "value": "", "count": 2}]

    first = payload["data"]["items"][0]
    assert first["name"] == "alpha.png"
    assert first["caption"] == "1girl, solo"
    assert first["tags"] == ["1girl", "solo"]
    assert first["caption_exists"] is True
    assert first["image_url"].startswith("/api/dataset-editor/image?")
    assert "root=" in first["image_url"]
    assert "image=alpha.png" in first["image_url"]

    second = payload["data"]["items"][1]
    assert second["name"] == "beta.jpg"
    assert second["caption"] == ""
    assert second["caption_exists"] is False


def test_dataset_editor_scan_groups_first_level_subfolders(tmp_path):
    char_dir = tmp_path / "10_character"
    style_dir = tmp_path / "20_style"
    char_dir.mkdir()
    style_dir.mkdir()
    make_image(char_dir / "alpha.png")
    make_image(style_dir / "beta.png")

    client = TestClient(app)
    response = client.post("/api/dataset-editor/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["categories"] == [
        {"name": "10_character", "value": "10_character", "count": 1},
        {"name": "20_style", "value": "20_style", "count": 1},
    ]
    assert data["items"][0]["category"] == "10_character"
    assert data["items"][1]["category"] == "20_style"


def test_dataset_editor_save_caption_creates_txt_caption(tmp_path):
    make_image(tmp_path / "alpha.png")

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "cat ears, smile"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["caption"] == "cat ears, smile"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "cat ears, smile"


def test_dataset_editor_batch_replace_remove_append_and_sort(tmp_path):
    make_image(tmp_path / "alpha.png")
    make_image(tmp_path / "beta.png")
    (tmp_path / "alpha.txt").write_text("solo, 1girl, old tag", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("solo, blue eyes", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png", "beta.png"],
            "append": ["masterpiece"],
            "remove": ["solo"],
            "replace": [{"from": "old tag", "to": "new tag"}],
            "sort": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 2
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "1girl, masterpiece, new tag"
    assert (tmp_path / "beta.txt").read_text(encoding="utf-8") == "blue eyes, masterpiece"


def test_dataset_editor_batch_cleans_obvious_caption_noise(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text(
        "white_background， 1girl, 1girl; basketball \\(object\\)\nsolo",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png"],
            "clean": True,
            "underscore_to_space": True,
            "strip_escape_chars": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["changed"] == 1
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == (
        "white background, 1girl, basketball (object), solo"
    )


def test_dataset_editor_undo_restores_single_caption_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("original tag", encoding="utf-8")

    client = TestClient(app)
    save = client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "changed tag"},
    )
    assert save.status_code == 200
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "changed tag"

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    payload = undo.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 1
    assert payload["data"]["items"][0]["caption"] == "original tag"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "original tag"


def test_dataset_editor_redo_reapplies_undone_caption_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("original tag", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "changed tag"},
    )
    client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    redo = client.post("/api/dataset-editor/redo", json={"root": str(tmp_path)})

    assert redo.status_code == 200
    payload = redo.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 1
    assert payload["data"]["items"][0]["caption"] == "changed tag"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "changed tag"


def test_dataset_editor_history_lists_saved_transactions(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("before", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "after"},
    )

    history = client.post("/api/dataset-editor/history", json={"root": str(tmp_path)})

    assert history.status_code == 200
    data = history.json()["data"]
    assert data["can_undo"] is True
    assert data["can_redo"] is False
    assert data["changes"][0]["label"] == "保存当前 caption"
    assert data["changes"][0]["items"][0]["before"] == "before"
    assert data["changes"][0]["items"][0]["after"] == "after"


def test_dataset_editor_undo_restores_missing_caption_after_create(tmp_path):
    make_image(tmp_path / "alpha.png")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "new tag"},
    )
    assert (tmp_path / "alpha.txt").is_file()

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    assert undo.json()["data"]["items"][0]["caption_exists"] is False
    assert not (tmp_path / "alpha.txt").exists()


def test_dataset_editor_undo_restores_batch_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    make_image(tmp_path / "beta.png")
    (tmp_path / "alpha.txt").write_text("solo, 1girl", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("solo, blue eyes", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png", "beta.png"],
            "append": ["masterpiece"],
            "remove": ["solo"],
            "replace": [],
            "sort": False,
        },
    )

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    assert undo.json()["data"]["changed"] == 2
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "solo, 1girl"
    assert (tmp_path / "beta.txt").read_text(encoding="utf-8") == "solo, blue eyes"


def test_dataset_editor_rejects_path_escape(tmp_path):
    make_image(tmp_path / "alpha.png")
    outside = tmp_path.parent / "outside.png"
    make_image(outside)

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "../outside.png", "caption": "bad"},
    )

    assert response.status_code == 400
    assert "outside dataset" in response.json()["detail"]


def test_dataset_editor_html_is_served_from_main_webui():
    client = TestClient(app)
    response = client.get("/dataset-editor.html")

    assert response.status_code == 200
    assert "dataset-editor.js" in response.text
    assert "旧版兼容" in response.text
    assert 'id="undo-edit"' in response.text
    assert 'id="redo-edit"' in response.text
    assert 'id="category-filter"' in response.text
    assert 'id="quick-tags"' in response.text
    assert 'id="tag-toggle"' in response.text
    assert 'id="side-tab-filter"' in response.text
    assert 'id="side-tab-quick"' in response.text
    assert 'id="side-tab-batch"' in response.text
    assert 'id="side-tab-clean"' in response.text
    assert 'id="apply-cleanup"' in response.text
    assert 'id="gallery-first-page"' in response.text
    assert 'id="gallery-prev-page"' in response.text
    assert 'id="gallery-page-input"' in response.text
    assert 'id="gallery-page-size"' in response.text
    assert 'value="auto"' in response.text
    assert 'id="gallery-next-page"' in response.text
    assert 'id="gallery-last-page"' in response.text
    assert 'id="thumbnail-fit"' in response.text
    assert 'id="change-list"' in response.text
    assert 'id="side-tab-tagger"' in response.text
    assert 'id="side-panel-tagger"' in response.text
    assert "<details" not in response.text


def test_legacy_tageditor_stays_legacy_only():
    client = TestClient(app)
    response = client.get("/tageditor.html")

    assert response.status_code == 200
    assert "tageditor.html.66da263e.js" in response.text
    assert "dataset-editor-entry.js" not in response.text
    assert 'name="sd-dataset-editor-script"' not in response.text


def test_native_tageditor_embeds_native_editor_in_trainer_shell():
    client = TestClient(app)
    response = client.get("/native-tageditor.html")

    assert response.status_code == 200
    assert "dataset-editor-entry.js" in response.text
    assert "dataset-editor.css" in response.text
    assert 'name="sd-dataset-editor-script"' in response.text
    assert 'href="/tageditor.md"' in response.text
    assert 'href="/native-tageditor.html"' in response.text
    assert "经典标签编辑" in response.text
    assert "原生标签编辑" in response.text


def test_trainer_sidebar_exposes_legacy_and_native_tag_editors():
    index = (ROOT / "frontend" / "dist" / "index.html").read_text(encoding="utf-8")
    tageditor = (ROOT / "frontend" / "dist" / "tageditor.html").read_text(encoding="utf-8")
    native_tageditor = (ROOT / "frontend" / "dist" / "native-tageditor.html").read_text(
        encoding="utf-8"
    )
    nav = (ROOT / "frontend" / "dist" / "assets" / "sd-nav-i18n.js").read_text(
        encoding="utf-8"
    )
    app_bundle = (ROOT / "frontend" / "dist" / "assets" / "app.547295de.js").read_text(
        encoding="utf-8"
    )

    assert 'href="/tageditor.md"' in index
    assert 'href="/native-tageditor.html"' in index
    assert 'href="/tageditor.md"' in tageditor
    assert 'href="/native-tageditor.html"' in tageditor
    assert 'href="/tageditor.md"' in native_tageditor
    assert 'href="/native-tageditor.html"' in native_tageditor
    assert "经典标签编辑" in index
    assert "原生标签编辑" in index
    assert "经典标签编辑" in tageditor
    assert "原生标签编辑" in tageditor
    assert "经典标签编辑" in native_tageditor
    assert "原生标签编辑" in native_tageditor
    assert '"/native-tageditor.html"' in app_bundle
    theme = json.loads(
        re.search(r"const WE=JSON\.parse\(`(?P<json>.*?)`\),x0=", app_bundle).group("json")
    )
    sidebar_text = json.dumps(theme["sidebar"], ensure_ascii=False)
    assert "经典标签编辑" in sidebar_text
    assert "原生标签编辑" in sidebar_text
    assert '经典标签编辑: "Legacy Tag Editor"' in nav
    assert '原生标签编辑: "Native Tag Editor"' in nav
    assert 'a[href="/dataset-editor.html"]' not in nav
    assert 'window.location.assign("/dataset-editor.html")' not in nav


def test_vuepress_theme_sidebar_json_stays_parseable():
    app_bundle = (ROOT / "frontend" / "dist" / "assets" / "app.547295de.js").read_text(
        encoding="utf-8"
    )
    match = re.search(r"const WE=JSON\.parse\(`(?P<json>.*?)`\),x0=", app_bundle)

    assert match is not None
    theme = json.loads(match.group("json"))
    sidebar_text = json.dumps(theme["sidebar"], ensure_ascii=False)
    assert "\u8bad\u7ec3" in sidebar_text
    assert "\u5de5\u5177\u4e0e\u8c03\u8bd5" in sidebar_text
    assert "\u6570\u636e\u96c6\u6253\u6807" in sidebar_text
    assert "经典标签编辑" in sidebar_text
    assert "原生标签编辑" in sidebar_text
    assert "LoRA \u811a\u672c\u5de5\u5177" in sidebar_text
    assert "\u5e2e\u52a9" in sidebar_text
    assert "\u5176\u4ed6" in sidebar_text
    assert "/native-tageditor.html" in sidebar_text


def test_nav_i18n_defaults_to_chinese_and_expands_training_group():
    nav = (ROOT / "frontend" / "dist" / "assets" / "sd-nav-i18n.js").read_text(
        encoding="utf-8"
    )

    assert 'return false;' in nav
    assert "ensureStableSidebarState" in nav
    assert "训练" in nav
    assert 'ul.style.display = ""' in nav
    assert 'li.dataset.sdForceExpanded = "1"' in nav


def test_patched_frontend_core_assets_are_not_immutable_cached():
    client = TestClient(app)

    for path in (
        "/assets/sd-nav-i18n.js",
        "/assets/app.547295de.js",
        "/assets/style.874872ce.css",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache, must-revalidate"


def test_embedded_native_editor_assets_keep_trainer_shell_contract():
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor-entry.js").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "de-shell de-shell-embedded" in script
    assert "theme-default-content" in script
    assert "打开内置编辑器" not in script
    assert "/proxy/tageditor/" not in script
    assert ".de-shell-embedded" in css
    assert "--de-accent: var(--c-brand" in css
    assert "grid-template-rows: 1fr" in css
    assert ".de-shell-embedded .de-workspace" in css
    assert "height: 100%" in css
    assert "startAfterShellSettles" in script
    assert "window.setTimeout(scheduleMount, 500)" in script
    assert "grid-template-columns: 320px minmax(520px, 1fr) 380px" in css
    assert ".de-gallery-empty" in css
    assert "@media (max-width: 1500px)" in css
    assert "grid-template-columns: 300px minmax(420px, 1fr)" in css
    assert ".de-shell-embedded .de-selection-actions" in css


def test_legacy_gradio_tageditor_is_opt_in():
    gui = (ROOT / "gui.py").read_text(encoding="utf-8")

    assert "--enable-legacy-tageditor" in gui
    assert "legacy_tageditor_enabled = args.enable_legacy_tageditor" in gui
    assert "Using native dataset editor at /dataset-editor.html" in gui


def test_dataset_editor_frontend_exposes_edit_efficiency_controls():
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )

    assert "/api/dataset-editor/undo" in script
    assert "/api/dataset-editor/redo" in script
    assert "/api/dataset-editor/history" in script
    assert "category-filter" in script
    assert "quick-tags" in script
    assert "applyCleanup" in script
    assert "underscore_to_space" in script
    assert "tagExpanded" in script
    assert "TAG_COLLAPSED_LIMIT" in script
    assert "GALLERY_PAGE_SIZE" in script
    assert 'const DEFAULT_GALLERY_PAGE_SIZE = "auto"' in script
    assert "galleryPageSize" in script
    assert "autoGalleryPageSize" in script
    assert "ResizeObserver" in script
    assert "galleryPage" in script
    assert "goToGalleryPage" in script
    assert "thumbnailFit" in script
    assert "change-list" in script
    assert "Ctrl+Z" in script
    assert "selectedPaths" in script
    assert "selectionMode" in script
    assert "toggleItemSelection" in script
    assert "selectedBatchItems" in script


def test_dataset_editor_css_keeps_desktop_workbench_layout():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )
    desktop_workspace = css.split(".de-workspace {", 1)[1].split("}", 1)[0]

    assert "--de-workbench-min-width" in css
    assert "grid-template-columns: 280px minmax(596px, 1fr) 420px" in css
    assert "grid-template-columns: 1fr" not in desktop_workspace


def test_dataset_editor_css_uses_readable_thumbnail_cards():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "grid-template-rows: 220px 20px" in css
    assert "minmax(220px, 1fr)" in css
    assert "object-fit: contain" in css
    assert ".de-gallery.is-cover .de-card img" in css


def test_dataset_editor_keeps_tag_cloud_out_of_default_filter_tab():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")

    filter_panel = html.split('id="side-panel-filter"', 1)[1].split('id="side-panel-quick"', 1)[0]
    quick_panel = html.split('id="side-panel-quick"', 1)[1]

    assert 'id="tag-list"' not in filter_panel
    assert 'id="tag-list"' in quick_panel


def test_dataset_editor_default_sidebar_starts_with_cleanup_workflow():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")

    clean_index = html.index('id="side-tab-clean"')
    batch_index = html.index('id="side-tab-batch"')
    filter_index = html.index('id="side-tab-filter"')
    quick_index = html.index('id="side-tab-quick"')

    assert clean_index < batch_index < filter_index < quick_index
    assert 'id="side-tab-clean" class="de-tab is-active"' in html


def test_dataset_editor_pager_controls_are_right_aligned():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert ".de-gallery-page-summary" in css
    assert ".de-gallery-page-controls" in css
    assert "justify-content: flex-end" in css


def test_dataset_editor_gallery_supports_bulk_selection_controls():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert 'id="selection-summary"' in html
    assert 'id="select-filtered"' in html
    assert 'id="select-page"' in html
    assert 'id="select-all"' in html
    assert 'id="clear-selection"' in html
    assert "selectAllItems" in (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )
    assert ".de-selection-bar" in css
    assert ".de-card-check" in css
    assert 'data-bulk-selected="true"' in css


def test_embedded_dataset_editor_compacts_toolbar_on_narrow_viewports():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "@media (max-width: 1080px)" in css
    assert ".de-shell-embedded .de-selection-bar" in css
    assert "grid-template-columns: 1fr" in css
    assert ".de-shell-embedded .de-gallery-page-controls" in css
    assert "justify-content: flex-start" in css
    assert "flex-wrap: wrap" in css


def test_embedded_dataset_editor_uses_native_workbench_visual_system():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert ".de-shell-embedded .de-gallery-wrap" in css
    assert "linear-gradient(180deg, var(--de-surface) 0%, var(--de-surface-muted) 100%)" in css
    assert "min-height: calc(100vh - 26px)" in css
    assert ".de-shell-embedded .de-gallery-empty::before" in css
    assert "grid-column: 1 / -1" in css
    assert ".de-shell-embedded .de-gallery:has(.de-gallery-empty)" in css
    assert "align-content: center" in css
    assert "content: \"\";" in css
    assert ".de-shell-embedded .de-editor textarea" in css
    assert "font-family: ui-monospace" in css
    assert ".de-shell-embedded .de-editor .de-primary" in css
    assert ".de-shell-embedded .de-change-list" in css
    assert "--de-card-shadow" in css
    assert ".de-shell-embedded .de-gallery-empty::after" in css
    assert ".de-shell-embedded .de-preview span::before" in css
    assert ".de-shell-embedded .de-panel h2::before" in css


def test_embedded_dataset_editor_keeps_side_panels_content_sized():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert ".de-shell-embedded .de-workspace" in css
    assert "align-items: start" in css
    assert ".de-shell-embedded .de-filter" in css
    assert ".de-shell-embedded .de-editor" in css
    assert "align-self: start" in css
    assert "max-height: calc(100vh - 26px)" in css


def test_dataset_editor_dataset_picker_is_prominent():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert 'class="de-dataset-card"' in html
    assert 'class="de-dataset-path"' in html
    assert html.index('id="dataset-path"') < html.index('class="de-gallery-wrap"')
    assert ".de-dataset-card" in css
    assert "min-height: 148px" in css
    assert "border-color: rgba(15, 118, 110, 0.36)" in css
    assert ".de-dataset-card::before" in css
    assert ".de-scope-card" in css
    assert ".de-dataset-actions button" in css
    assert "min-height: 42px" in css
    assert ".de-dataset-path:focus-within" in css


def test_dataset_editor_left_sidebar_owns_dataset_scope_and_tagger():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )

    sidebar = html.split('class="de-panel de-filter"', 1)[1].split('class="de-gallery-wrap"', 1)[0]
    editor = html.split('class="de-panel de-editor"', 1)[1]

    assert 'class="de-dataset-card"' in sidebar
    assert 'class="de-scope-card"' in sidebar
    assert sidebar.index('id="category-filter"') < sidebar.index('id="side-tab-clean"')
    assert 'id="side-tab-tagger"' in sidebar
    assert 'id="side-panel-tagger"' in sidebar
    assert "打标" in sidebar
    assert "自动打标" not in editor
    assert "tagger: document.getElementById" in script
    assert ".de-scope-card" in css
    assert "grid-template-columns: repeat(5, 1fr)" in css


def test_dataset_editor_tagger_panel_exposes_local_and_api_caption_controls():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )
    entry = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor-entry.js").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert 'id="tagger-provider"' in html
    assert 'id="tagger-caption-type"' in html
    assert 'id="tagger-conflict"' in html
    assert 'id="tagger-model"' in html
    assert 'class="de-tagger-card de-tagger-card--primary"' in html
    assert 'class="de-tagger-row de-tagger-row--split"' in html
    assert 'class="de-tagger-model-card"' in html
    assert 'class="de-tagger-flags"' in html
    assert 'id="tagger-api-endpoint"' not in html
    assert 'id="tagger-api-key"' not in html
    assert 'id="tagger-api-model"' not in html
    assert 'id="tagger-api-prompt"' not in html
    assert 'id="run-tagger"' in html
    assert 'id="tagger-provider"' in entry
    assert 'class="de-tagger-card de-tagger-card--primary"' in entry
    assert 'class="de-tagger-model-card"' in entry
    assert 'id="tagger-api-endpoint"' not in entry
    assert 'id="tagger-api-key"' not in entry
    assert 'id="tagger-api-model"' not in entry
    assert 'id="tagger-api-prompt"' not in entry
    assert 'id="run-tagger"' in entry
    assert "/api/dataset-editor/tag" in script
    assert "applyTagger" in script
    assert "taggerProvider" in script
    assert "tagger-caption-type" in script
    assert "loadUiConfigs" in script
    assert "dataset_tagger_api_endpoint" in script
    assert "dataset_tagger_api_key" in script
    assert "dataset_tagger_api_model" in script
    assert "dataset_tagger_api_prompt" in script
    assert ".de-tagger-grid" in css
    assert ".de-tagger-card--primary" in css
    assert ".de-tagger-row--split" in css
    assert ".de-tagger-model-card" in css
    assert ".de-tagger-flags" in css


def test_ui_settings_exposes_dataset_tagger_api_config():
    settings = (ROOT / "frontend" / "dist" / "assets" / "settings.html.06993f96.js").read_text(
        encoding="utf-8"
    )
    app_js = (ROOT / "frontend" / "dist" / "assets" / "app.547295de.js").read_text(encoding="utf-8")
    settings_html = (ROOT / "frontend" / "dist" / "other" / "settings.html").read_text(
        encoding="utf-8"
    )

    assert "dataset_tagger_api_endpoint" in settings
    assert "dataset_tagger_api_key" in settings
    assert "dataset_tagger_api_model" in settings
    assert "dataset_tagger_api_prompt" in settings
    assert "./settings.html.06993f96.js?v=dataset-tagger-api" in app_js
    assert "/assets/app.547295de.js?v=dataset-tagger-api" in settings_html


def test_dataset_editor_tag_endpoint_writes_local_tags_and_api_caption(tmp_path, monkeypatch):
    make_image(tmp_path / "alpha.png")
    make_image(tmp_path / "beta.png")
    (tmp_path / "alpha.txt").write_text("old tag", encoding="utf-8")

    from mikazuki import dataset_editor

    def fake_local_tags(_image_path, _req):
        return "blue hair, smile"

    def fake_api_caption(_image_path, req):
        assert req.api_key == "secret"
        assert req.api_model == "vision-model"
        return "a natural language caption"

    monkeypatch.setattr(dataset_editor, "generate_local_tags", fake_local_tags)
    monkeypatch.setattr(dataset_editor, "generate_api_caption", fake_api_caption)

    client = TestClient(app)
    local = client.post(
        "/api/dataset-editor/tag",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png", "beta.png"],
            "provider": "local",
            "caption_type": "tags",
            "on_conflict": "append",
            "additional_tags": "best quality",
        },
    )

    assert local.status_code == 200
    assert local.json()["status"] == "success"
    assert local.json()["data"]["changed"] == 2
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == (
        "old tag, blue hair, smile, best quality"
    )
    assert (tmp_path / "beta.txt").read_text(encoding="utf-8") == "blue hair, smile, best quality"

    api = client.post(
        "/api/dataset-editor/tag",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png"],
            "provider": "api",
            "caption_type": "caption",
            "on_conflict": "copy",
            "api_endpoint": "https://example.test/v1",
            "api_key": "secret",
            "api_model": "vision-model",
        },
    )

    assert api.status_code == 200
    assert api.json()["status"] == "success"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "a natural language caption"

    history = client.post("/api/dataset-editor/history", json={"root": str(tmp_path)})
    labels = [change["label"] for change in history.json()["data"]["changes"]]
    assert labels[:2] == ["API 自然语言打标", "本地标签打标"]

