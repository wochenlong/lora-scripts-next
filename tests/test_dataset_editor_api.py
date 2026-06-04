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
    assert payload["data"]["tags"] == [
        {"tag": "1girl", "count": 1},
        {"tag": "solo", "count": 1},
    ]
    assert payload["data"]["categories"] == [
        {"name": "根目录", "value": "", "count": 2}
    ]

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
        json={
            "root": str(tmp_path),
            "image": "alpha.png",
            "caption": "cat ears, smile",
        },
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
    assert (tmp_path / "alpha.txt").read_text(
        encoding="utf-8"
    ) == "1girl, masterpiece, new tag"
    assert (tmp_path / "beta.txt").read_text(
        encoding="utf-8"
    ) == "blue eyes, masterpiece"


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
    assert (
        'src="/assets/app.547295de.js?v=20260604-native-tageditor-2"' in response.text
    )
    assert 'href="/tageditor.md"' in response.text
    assert 'href="/native-tageditor.html"' in response.text
    assert "经典标签编辑" in response.text
    assert "原生标签编辑" in response.text


def test_native_tageditor_uses_native_vuepress_page_data():
    native_tageditor = (ROOT / "frontend" / "dist" / "native-tageditor.html").read_text(
        encoding="utf-8"
    )
    native_page_data = (
        ROOT / "frontend" / "dist" / "assets" / "native-tageditor.html.native.js"
    )
    native_page_component = (
        ROOT / "frontend" / "dist" / "assets" / "native-tageditor.html.page.js"
    )
    app_bundle = (ROOT / "frontend" / "dist" / "assets" / "app.547295de.js").read_text(
        encoding="utf-8"
    )

    assert native_page_data.exists()
    assert native_page_component.exists()
    page_data = native_page_data.read_text(encoding="utf-8")
    parsed_page_data = json.loads(
        re.search(r"JSON\.parse\((.*)\);export", page_data).group(1)
    )
    parsed_page_data = json.loads(parsed_page_data)
    assert parsed_page_data["key"] == "v-native-tageditor"
    assert parsed_page_data["title"] == "原生标签编辑"
    assert parsed_page_data["frontmatter"] == {}
    assert parsed_page_data["frontmatter"].get("type") != "iframe"
    assert (
        '"v-native-tageditor":()=>wt(()=>import("./native-tageditor.html.native.js?v=20260604-native-tageditor-2")'
        in app_bundle
    )
    assert (
        '"v-native-tageditor":Jt(()=>wt(()=>import("./native-tageditor.html.page.js?v=20260604-native-tageditor-2")'
        in app_bundle
    )
    assert app_bundle.count('["v-native-tageditor","/native-tageditor.html"') == 1
    assert (
        '["v-native-tageditor","/native-tageditor.html",{title:"原生标签编辑"}'
        in app_bundle
    )
    assert (
        'rel="modulepreload" href="/assets/tageditor.html.66da263e.js"'
        not in native_tageditor
    )
    assert (
        'rel="modulepreload" href="/assets/tageditor.html.173f1b6a.js"'
        not in native_tageditor
    )


def test_tageditor_embeds_native_editor_in_trainer_shell():
    script = (
        ROOT / "frontend" / "dist" / "assets" / "dataset-editor-entry.js"
    ).read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "de-shell de-shell-embedded" in script
    assert "theme-default-content" in script
    assert "打开内置编辑器" not in script
    assert "/proxy/tageditor/" not in script
    assert 'document.getElementById("sd-native-editor-entry")' in script
    assert "initializeMountedEditor()" in script
    assert "window.sdDatasetEditor?.init?.()" in script
    assert "observer.disconnect()" not in script
    assert ".de-shell-embedded" in css
    assert "--de-accent: var(--c-brand" in css
    assert "grid-template-rows: 1fr" in css
    assert ".de-shell-embedded .de-workspace" in css
    assert "height: 100%" in css
    assert "grid-template-columns: 280px minmax(0, 1fr) 300px" in css
    assert ".de-gallery-empty" in css
    assert "@media (max-width: 1120px)" in css
    assert "flex-wrap: wrap;" in css
    assert ".de-shell-embedded .de-selection-actions" in css


def test_embedded_dataset_editor_medium_width_layout_avoids_overlap():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    medium_breakpoint = css.split("@media (max-width: 1120px)", 1)[1].split(
        "@media (max-width: 920px)", 1
    )[0]
    assert "display: flex;" in medium_breakpoint
    assert "flex-wrap: wrap;" in medium_breakpoint
    assert ".de-shell-embedded .de-filter" in medium_breakpoint
    assert "flex: 0 0 280px;" in medium_breakpoint
    assert ".de-shell-embedded .de-editor" in medium_breakpoint
    assert "flex: 1 0 100%;" in medium_breakpoint


def test_embedded_dataset_editor_dark_mode_tokens_are_explicit():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "html.dark .de-shell-embedded" in css
    assert "--de-bg: #111827;" in css
    assert "--de-surface: #1f2937;" in css
    assert "--de-text: #e5e7eb;" in css
    assert "html.dark .de-shell-embedded .de-preview" in css
    assert "html.dark .de-shell-embedded .de-tag" in css


def test_embedded_dataset_editor_pager_wraps_before_buttons_overflow():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    pager_breakpoint = css.split("@media (max-width: 1260px)", 1)[1].split(
        "html.dark .de-shell-embedded", 1
    )[0]
    assert ".de-shell-embedded .de-gallery-pager" in pager_breakpoint
    assert "grid-template-columns: 1fr;" in pager_breakpoint
    assert ".de-shell-embedded .de-gallery-page-controls" in pager_breakpoint
    assert "flex-wrap: wrap;" in pager_breakpoint
    assert "justify-content: flex-start;" in pager_breakpoint


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
    assert "window.sdDatasetEditor" in script
    assert "function initDatasetEditor()" in script
    assert "dataset.sdDatasetEditorBound" in script
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
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )

    filter_panel = html.split('id="side-panel-filter"', 1)[1].split(
        'id="side-panel-quick"', 1
    )[0]
    quick_panel = html.split('id="side-panel-quick"', 1)[1]

    assert 'id="tag-list"' not in filter_panel
    assert 'id="tag-list"' in quick_panel


def test_dataset_editor_default_sidebar_starts_with_cleanup_workflow():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )

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
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert 'id="selection-summary"' in html
    assert 'id="select-filtered"' in html
    assert 'id="select-page"' in html
    assert 'id="select-all"' in html
    assert 'id="clear-selection"' in html
    assert "selectAllItems" in (
        ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js"
    ).read_text(encoding="utf-8")
    assert ".de-selection-bar" in css
    assert ".de-card-check" in css
    assert 'data-bulk-selected="true"' in css


def test_embedded_dataset_editor_compacts_toolbar_on_narrow_viewports():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert "@media (max-width: 920px)" in css
    assert "@media (max-width: 1260px)" in css
    assert ".de-shell-embedded .de-selection-bar" in css
    assert "grid-template-columns: 1fr" in css
    assert ".de-shell-embedded .de-gallery-page-controls" in css
    assert "justify-content: flex-start" in css
    assert "flex-wrap: wrap" in css


def test_dataset_editor_dataset_picker_is_prominent():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )
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
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )

    sidebar = html.split('class="de-panel de-filter"', 1)[1].split(
        'class="de-gallery-wrap"', 1
    )[0]
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


def test_dataset_editor_hides_quick_tags_but_keeps_tag_filter():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )
    entry = (
        ROOT / "frontend" / "dist" / "assets" / "dataset-editor-entry.js"
    ).read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    assert 'class="de-quick-tags-title"' in html
    assert 'class="de-quick-tags-title"' in entry
    assert ".de-quick-tags-title" in css
    assert ".de-quick-tags" in css
    assert ".de-quick-custom" in css
    assert "display: none;" in css
    assert "按标签筛选" in html
    assert "按标签筛选" in entry
    assert 'id="tag-list"' in html
    assert 'id="tag-list"' in entry


def test_nav_i18n_keeps_native_tag_editor_entry_distinct():
    script = (ROOT / "frontend" / "dist" / "assets" / "sd-nav-i18n.js").read_text(
        encoding="utf-8"
    )

    assert "function ensureTagEditorLinks()" in script
    assert "经典标签编辑" in script
    assert "原生标签编辑" in script
    assert "textNodes.slice(1).forEach" in script
    assert 'native.href = "/native-tageditor.html"' in script
    assert "ensureTagEditorLinks();" in script


def test_dataset_editor_tagger_panel_can_append_trigger_words():
    html = (ROOT / "frontend" / "dist" / "dataset-editor.html").read_text(
        encoding="utf-8"
    )
    entry = (
        ROOT / "frontend" / "dist" / "assets" / "dataset-editor-entry.js"
    ).read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.js").read_text(
        encoding="utf-8"
    )

    for markup in (html, entry):
        assert 'id="tagger-trigger-tags"' in markup
        assert 'id="apply-tagger-trigger"' in markup
        assert "额外触发词" in markup
        assert "预留位置" not in markup

    assert "taggerTrigger" in script
    assert "applyTaggerTrigger" in script
    assert "额外触发词" in script
    assert "append: splitTags(el.taggerTrigger.value)" in script


def test_dataset_editor_embedded_dark_mode_keeps_text_and_controls_readable():
    css = (ROOT / "frontend" / "dist" / "assets" / "dataset-editor.css").read_text(
        encoding="utf-8"
    )

    embedded_shell = css.split(".de-shell-embedded {", 1)[1].split("}", 1)[0]
    embedded_inputs = css.split(".de-shell-embedded .de-dataset-path,", 1)[1].split(
        "}", 1
    )[0]
    embedded_buttons = css.split(".de-shell-embedded button {", 1)[1].split("}", 1)[0]
    embedded_primary = css.split(".de-shell-embedded .de-primary {", 1)[1].split(
        "}", 1
    )[0]
    embedded_cards = css.split(".de-shell-embedded .de-card,", 1)[1].split("}", 1)[0]

    assert "color: var(--de-text)" in embedded_shell
    assert "background: var(--de-input-bg)" in embedded_inputs
    assert "color: var(--de-text)" in embedded_inputs
    assert "background: var(--de-control-bg)" in embedded_buttons
    assert "color: var(--de-control-text)" in embedded_buttons
    assert "color: #fff" in embedded_primary
    assert "color: var(--de-text)" in embedded_cards
