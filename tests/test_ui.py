"""Window integration tests (needs a display; skipped headless).

The window is withdrawn so nothing flashes. Dialogs are mocked so a failure
can never block on a popup.
"""

import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ui.main_window import MainWindow

DATA = Path(__file__).resolve().parent / "data"

VCF = """\
BEGIN:VCARD
VERSION:3.0
FN:Amy Beta
ORG:Alpha
TEL;TYPE=CELL:111
EMAIL:amy@a.co
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Zed Alpha
ORG:Zeta
EMAIL:zed@z.co
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Max NoMail
TEL:333
ADR:;;Street;City;R;1;C
END:VCARD
"""


class TestMainWindow(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        self._state_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._state_tmp.cleanup)
        self._prev_state = os.environ.get("VCARD_READER_STATE")
        os.environ["VCARD_READER_STATE"] = str(
            Path(self._state_tmp.name) / "state.json")
        self.addCleanup(self._restore_state_env)
        try:
            self.app = MainWindow()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.addCleanup(self._close)
        self.app.root.withdraw()
        self.app.root.update_idletasks()

        self.tmp = mock.patch("ui.main_window.filedialog")
        self.filedialog = self.tmp.start()
        self.addCleanup(self.tmp.stop)

        self.msg = mock.patch("ui.main_window.messagebox")
        self.messagebox = self.msg.start()
        self.addCleanup(self.msg.stop)

        self.file = self._write_vcf("in.vcf", VCF)
        self.app.load_file(self.file)

    def _close(self):
        try:
            self.app.root.destroy()
        except tk.TclError:
            pass

    def _restore_state_env(self):
        import os
        if self._prev_state is None:
            os.environ.pop("VCARD_READER_STATE", None)
        else:
            os.environ["VCARD_READER_STATE"] = self._prev_state

    def _write_vcf(self, name, text):
        import tempfile
        from pathlib import Path
        path = Path(tempfile.gettempdir()) / f"vcard-reader-test-{name}"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return str(path)

    def rows(self):
        return [self.app.tree.item(i, "text")
                for i in self.app.tree.get_children()]

    def details(self):
        return self.app.details.get("1.0", "end-1c")

    def click_y(self, index):
        # bbox() needs a mapped window; park it far offscreen so nothing shows.
        self.app.root.geometry("+32000+32000")
        self.app.root.deiconify()
        self.app.root.update()
        iid = self.app.tree.get_children()[index]
        box = self.app.tree.bbox(iid)
        assert box, "row has no screen coordinates"
        _x, y, _w, h = box
        return y + h // 2

    # ----- loading -----

    def test_load_lists_all_sorted(self):
        self.assertEqual(self.rows(), ["Amy Beta", "Max NoMail", "Zed Alpha"])
        self.assertIn("3 contacts", self.app.status_left.cget("text"))

    def test_load_selects_first_and_shows_details(self):
        self.assertEqual(self.app.selected.display_name, "Amy Beta")
        self.assertIn("Amy Beta", self.details())
        self.assertIn("111", self.details())

    # ----- search / filter / sort -----

    def test_search_filters(self):
        self.app.search_var.set("zed")
        self.app.apply_filter()
        self.assertEqual(self.rows(), ["Zed Alpha"])
        self.assertEqual(self.app.selected.display_name, "Zed Alpha")

    def test_type_filter(self):
        self.app.type_var.set("Has phone")
        self.app.apply_filter()
        self.assertEqual(self.rows(), ["Amy Beta", "Max NoMail"])

    def test_sort_menu(self):
        self.app.sort_var.set("Name Z–A")
        self.app.apply_filter()
        self.assertEqual(self.rows(), ["Zed Alpha", "Max NoMail", "Amy Beta"])

    def test_no_match_shows_empty_state(self):
        self.app.search_var.set("no-such-person")
        self.app.apply_filter()
        self.assertEqual(self.rows(), [])
        self.assertIsNone(self.app.selected)
        self.assertIn("No matches", self.details())

    # ----- mouse -----

    def test_right_click_selects_row(self):
        with mock.patch("tkinter.Menu"):
            event = SimpleNamespace(x=5, y=self.click_y(2),
                                    x_root=100, y_root=100)
            self.app._on_list_right_click(event)
        self.assertEqual(self.app.selected.display_name, "Zed Alpha")

    def test_drag_moves_selection(self):
        event = SimpleNamespace(y=self.click_y(1))
        self.app._on_list_drag(event)
        self.assertEqual(self.app.selected.display_name, "Max NoMail")
        self.assertIn("Max NoMail", self.details())

    # ----- actions -----

    def test_copy_details(self):
        self.app._copy_details()
        self.assertIn("Amy Beta", self.app.root.clipboard_get())

    def test_export_selected(self):
        out = self._write_vcf("out-single.vcf", "")
        self.filedialog.asksaveasfilename.return_value = out
        self.app._export_selected()
        from pathlib import Path
        text = Path(out).read_text(encoding="utf-8")
        self.assertIn("Amy Beta", text)
        self.assertNotIn("Zed Alpha", text)

    def test_drop_vcf_loads(self):
        self.app.search_var.set("zzz")
        self.app.apply_filter()
        self.assertEqual(self.rows(), [])
        self.app._on_drop([self.file])
        self.assertEqual(len(self.app.contacts), 3)
        self.app.search_var.set("")
        self.app.apply_filter()
        self.assertEqual(len(self.rows()), 3)

    def test_drop_folder_loads_vcf_inside(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.vcf").write_text(VCF, encoding="utf-8")
            (Path(tmp) / "notes.txt").write_text("not a vcard", encoding="utf-8")
            self.app._on_drop([tmp])
        self.assertEqual(len(self.rows()), 3)

    def test_drop_non_vcf_ignored(self):
        before = self.rows()
        self.app._on_drop(["C:\\Windows\\notepad.exe"])
        self.assertEqual(self.rows(), before)
        self.assertIn("no .vcf", self.app.status_left.cget("text"))

    def test_action_states_follow_selection(self):
        for btn in (self.app.reload_btn, self.app.export_btn, self.app.copy_btn):
            self.assertNotIn("disabled", btn.state())
        self.app.search_var.set("no-such-person")
        self.app.apply_filter()
        self.assertNotIn("disabled", self.app.reload_btn.state())
        self.assertIn("disabled", self.app.export_btn.state())
        self.assertIn("disabled", self.app.copy_btn.state())
        self.assertEqual(self.app.file_menu.entrycget("Reload", "state"), "normal")
        self.assertEqual(
            self.app.edit_menu.entrycget("Copy details", "state"), "disabled")

    def test_action_states_disabled_without_file(self):
        import os
        from pathlib import Path as _Path
        # setUp already saved a recent file; clear it so this starts empty.
        _Path(os.environ["VCARD_READER_STATE"]).unlink(missing_ok=True)
        try:
            fresh = MainWindow()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        try:
            fresh.root.withdraw()
            for btn in (fresh.reload_btn, fresh.export_btn, fresh.copy_btn):
                self.assertIn("disabled", btn.state())
            self.assertEqual(fresh.file_menu.entrycget("Reload", "state"),
                             "disabled")
            self.assertEqual(fresh.edit_menu.entrycget("Copy details", "state"),
                             "disabled")
        finally:
            try:
                fresh.root.destroy()
            except tk.TclError:
                pass

    def test_nasty_file_reports_problems(self):
        self.app.load_file(str(DATA / "nasty.vcf"))
        self.assertTrue(self.messagebox.showerror.called)
        _args, kwargs = self.messagebox.showerror.call_args
        text = (_args[1] if len(_args) > 1 else "") + str(kwargs)
        self.assertIn("line", text)
        self.assertIn("Fix:", text)
        names = self.rows()
        self.assertIn("Survivor", names)

    def test_clean_file_reports_nothing(self):
        self.messagebox.showerror.assert_not_called()
        self.messagebox.showinfo.assert_not_called()

    def test_drag_near_edges_scrolls(self):
        cards = "".join(
            f"BEGIN:VCARD\nVERSION:3.0\nFN:Person {i:02d}\nTEL:{i}\nEND:VCARD\n"
            for i in range(60))
        self.app.load_file(self._write_vcf("many.vcf", cards))
        self.app.root.geometry("+32000+32000")
        self.app.root.deiconify()
        self.app.root.update()
        self.assertEqual(self.app.tree.yview()[0], 0.0)
        self.app._on_list_drag(SimpleNamespace(y=10 ** 6))
        self.app._cancel_drag_scroll()
        scrolled = self.app.tree.yview()[0]
        self.assertGreater(scrolled, 0.0)
        self.app._on_list_drag(SimpleNamespace(y=-10 ** 6))
        self.app._cancel_drag_scroll()
        self.assertLess(self.app.tree.yview()[0], scrolled)

    def test_enter_copies_details(self):
        self.app._on_enter()
        self.assertIn("Amy Beta", self.app.root.clipboard_get())

    def test_copy_as_vcard(self):
        self.app._copy_vcard()
        text = self.app.root.clipboard_get()
        self.assertIn("BEGIN:VCARD", text)
        self.assertIn("Amy Beta", text)

    def test_status_shows_counts(self):
        self.assertIn("1 phone", self.app.status_right.cget("text"))
        self.assertIn("1 email", self.app.status_right.cget("text"))

    def test_zoom_changes_detail_size(self):
        before = self.app.detail_font.cget("size")
        self.app._zoom(1)
        self.assertEqual(self.app.detail_font.cget("size"), before + 1)
        for _ in range(30):
            self.app._zoom(-1)
        self.assertGreaterEqual(self.app.detail_font.cget("size"), 8)

    def test_details_show_version_and_source(self):
        self.app.load_file(str(DATA / "vcard30.vcf"))
        details = self.details()
        self.assertIn("vCard 3.0", details)
        self.assertIn("vcard30.vcf", details)

    def menu_labels(self, menu):
        return [menu.entrycget(i, "label")
                for i in range(menu.index(tk.END) + 1)
                if menu.type(i) != "separator"]
    def test_recent_menu_updated_on_load(self):
        names = self.menu_labels(self.app.recent_menu)
        self.assertTrue(any("in.vcf" in label for label in names))
        self.assertTrue(any(Path(label).is_absolute() for label in names))

    def test_clear_recents(self):
        import os
        from pathlib import Path as _Path
        state_file = _Path(os.environ["VCARD_READER_STATE"])
        self.assertTrue(state_file.is_file())
        self.assertIn("Clear recents", self.menu_labels(self.app.recent_menu))
        self.app._clear_recent()
        self.assertEqual(self.app.state.get("recent"), [])
        self.assertEqual(self.menu_labels(self.app.recent_menu), ["(Empty)"])
        self.assertIn("cleared", self.app.status_left.cget("text").lower())
        # Guard: temp settings dir outside ASDK must survive.
        self.assertTrue(state_file.parent.is_dir())

    def test_export_all(self):
        out = self._write_vcf("out-all.vcf", "")
        self.filedialog.asksaveasfilename.return_value = out
        self.app._export_all()
        from pathlib import Path
        text = Path(out).read_text(encoding="utf-8")
        for name in ("Amy Beta", "Max NoMail", "Zed Alpha"):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
