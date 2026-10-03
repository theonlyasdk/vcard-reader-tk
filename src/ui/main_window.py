"""Two-pane vCard reader window: list on the left, details on the right."""

import tkinter as tk
import webbrowser
from tkinter import filedialog, font, messagebox, ttk
from pathlib import Path

from core import (
    MAX_RECENT,
    TYPE_FILTERS,
    SORT_OPTIONS,
    filter_contacts,
    load_state,
    parse_file_with_issues,
    save_state,
    sort_contacts,
)
from .dpi import setup_window_dpi
from .file_drop import enable_file_drop

SEARCH_PLACEHOLDER = "Search"


def _light(size, weight="normal"):
    for family in ("Segoe UI Light", "Segoe UI Semilight", "Segoe UI"):
        try:
            font.Font(family=family, size=size, weight=weight)
            return (family, size, weight)
        except Exception:
            continue
    return ("Segoe UI", size, weight)


class MainWindow:
    def __init__(self, initial_file=None):
        self.root = tk.Tk()
        self.root.title("vCard Reader")
        setup_window_dpi(self.root, base_width=1000, base_height=640,
                         min_width=720, min_height=420)
        self._use_segoe_everywhere()

        self.contacts = []
        self.filtered = []
        self.selected = None
        self.current_files = []
        self._copy_seq = 0
        self.search_var = tk.StringVar()
        self.type_var = tk.StringVar(value=TYPE_FILTERS[0])
        self.sort_var = tk.StringVar(value=SORT_OPTIONS[0])
        self._search_after = None
        self._drag_scroll_job = None
        self.state = load_state()

        self._create_menu()
        self._create_toolbar()
        self._create_body()
        self._create_statusbar()
        self.drop_enabled = enable_file_drop(self.root, self._on_drop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        if initial_file:
            startup = [initial_file]
        else:
            startup = [p for p in self.state.get("recent", [])
                       if Path(p).is_file()]
        if startup:
            self.load_files(startup)
        else:
            self._render_list()
            self._show_empty()

    # ----- setup -----

    def _use_segoe_everywhere(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont",
                     "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont",
                     "TkMenuFont", "TkTooltipFont"):
            try:
                f = font.nametofont(name)
                f.configure(family="Segoe UI", size=9)
            except Exception:
                pass
        self.f_heading = _light(20)
        self.f_sub = _light(12)
        self.f_section = _light(11)
        self.f_body = ("Segoe UI", 10)
        self.f_small = ("Segoe UI", 8)
        self.detail_font = font.Font(family="Segoe UI", size=10)
        try:
            self.root.option_add("*Font", self.f_body)
        except Exception:
            pass

    # ----- menu -----

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu
        file_menu.add_command(label="Open…", accelerator="Ctrl+O", command=self._open_dialog)
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open recent", menu=self.recent_menu)
        file_menu.add_command(label="Reload", accelerator="F5", command=self._reload)
        file_menu.add_command(label="Export selected…", accelerator="Ctrl+S",
                              command=self._export_selected)
        file_menu.add_command(label="Export all…", command=self._export_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)

        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.edit_menu = edit_menu
        edit_menu.add_command(label="Copy details", accelerator="Ctrl+C",
                              command=self._copy_details)
        edit_menu.add_command(label="Copy as vCard", command=self._copy_vcard)
        edit_menu.add_command(label="Copy phone", command=self._copy_phone)
        edit_menu.add_command(label="Copy email", command=self._copy_email)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select all", accelerator="Ctrl+A",
                              command=self._select_all)

        self.view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_command(label="Sort: placeholder (rebuilt below)")
        self._rebuild_sort_menu()

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

        self.root.bind_all("<Control-o>", lambda e: self._open_dialog())
        self.root.bind_all("<Control-s>", lambda e: self._export_selected())
        self.root.bind_all("<Control-a>", self._on_ctrl_a)
        self.root.bind_all("<Control-c>", self._on_ctrl_c)
        self.root.bind_all("<Control-f>", self._on_ctrl_f)
        self.root.bind_all("<Control-plus>", lambda e: self._zoom(1))
        self.root.bind_all("<Control-equal>", lambda e: self._zoom(1))
        self.root.bind_all("<Control-minus>", lambda e: self._zoom(-1))
        self.root.bind_all("<F5>", lambda e: self._reload())
        self._rebuild_recent()

    def _rebuild_sort_menu(self):
        self.view_menu.delete(0, tk.END)
        sort_menu = tk.Menu(self.view_menu, tearoff=0)
        self.view_menu.add_cascade(label="Sort by", menu=sort_menu)
        for option in SORT_OPTIONS:
            sort_menu.add_radiobutton(label=option, variable=self.sort_var,
                                      value=option, command=self.apply_filter)

    # ----- toolbar (quick actions) -----

    def _create_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6, 8, 2))
        bar.pack(side=tk.TOP, fill=tk.X)
        buttons = {}
        for label, command in (("Open", self._open_dialog),
                               ("Reload", self._reload),
                               ("Export", self._export_selected),
                               ("Copy", self._copy_details)):
            buttons[label] = ttk.Button(bar, text=label, command=command)
            buttons[label].pack(side=tk.LEFT, padx=(0, 6))
        self.reload_btn = buttons["Reload"]
        self.export_btn = buttons["Export"]
        self.copy_btn = buttons["Copy"]

    # ----- body -----

    def _create_body(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.paned = paned

        left = ttk.Frame(paned, padding=(0, 0, 4, 0))
        paned.add(left, weight=1)

        search = ttk.Entry(left, textvariable=self.search_var, width=24)
        search.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        search.insert(0, SEARCH_PLACEHOLDER)
        search.configure(foreground="gray")
        search.bind("<FocusIn>", self._search_focus_in)
        search.bind("<FocusOut>", self._search_focus_out)
        search.bind("<KeyRelease>", self._search_changed)
        search.bind("<Escape>", self._search_clear)
        self.search_entry = search

        filters = ttk.Frame(left)
        filters.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        self.type_button = ttk.Menubutton(filters, textvariable=self.type_var,
                                          direction="below")
        self.type_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        type_menu = tk.Menu(self.type_button, tearoff=0)
        for option in TYPE_FILTERS:
            type_menu.add_radiobutton(label=option, variable=self.type_var,
                                      value=option, command=self.apply_filter)
        self.type_button["menu"] = type_menu

        self.sort_button = ttk.Menubutton(filters, textvariable=self.sort_var,
                                          direction="below")
        self.sort_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sort_menu = tk.Menu(self.sort_button, tearoff=0)
        for option in SORT_OPTIONS:
            sort_menu.add_radiobutton(label=option, variable=self.sort_var,
                                      value=option, command=self.apply_filter)
        self.sort_button["menu"] = sort_menu

        list_frame = ttk.Frame(left)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(list_frame, columns=("sub",), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("sub", text="Details")
        self.tree.column("#0", width=150, anchor=tk.W)
        self.tree.column("sub", width=140, anchor=tk.W)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._on_list_right_click)
        self.tree.bind("<B1-Motion>", self._on_list_drag)
        self.tree.bind("<ButtonRelease-1>", self._cancel_drag_scroll)
        self.tree.bind("<Return>", self._on_enter)
        self.tree.tag_configure("stripe", background="#f0f4f8")

        right = ttk.Frame(paned, padding=(12, 4, 4, 0))
        paned.add(right, weight=2)

        self.details = tk.Text(right, wrap=tk.WORD, relief=tk.FLAT,
                               padx=4, pady=4, state=tk.DISABLED,
                               font=self.detail_font)
        detail_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL,
                                      command=self.details.yview)
        self.details.configure(yscrollcommand=detail_scroll.set)
        self.details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.details.tag_configure("h1", font=self.f_heading, spacing3=2)
        self.details.tag_configure("sub", font=self.f_sub, foreground="#555555")
        self.details.tag_configure("section", font=self.f_section,
                                   foreground="#444444", spacing1=10, spacing3=2)
        self.details.tag_configure("label", font=("Segoe UI", 9),
                                   foreground="#777777")
        self.details.tag_configure("value", font=self.detail_font)
        self.details.tag_configure("dim", font=self.detail_font, foreground="#666666")

    # ----- status bar -----

    def _create_statusbar(self):
        bar = ttk.Frame(self.root, relief=tk.SUNKEN, padding=(8, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_left = ttk.Label(bar, text="No file", font=self.f_small)
        self.status_left.pack(side=tk.LEFT)
        self.status_right = ttk.Label(bar, text="", font=self.f_small)
        self.status_right.pack(side=tk.RIGHT)

    def _set_status(self, left=None, right=None):
        if left is not None:
            self.status_left.configure(text=left)
        if right is not None:
            self.status_right.configure(text=right)

    # ----- search -----

    def _search_text(self):
        text = self.search_var.get()
        if text == SEARCH_PLACEHOLDER:
            return ""
        return text.strip().lower()

    def _search_focus_in(self, _event=None):
        if self.search_var.get() == SEARCH_PLACEHOLDER:
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(foreground="black")

    def _search_focus_out(self, _event=None):
        if not self.search_var.get().strip():
            self.search_var.set(SEARCH_PLACEHOLDER)
            self.search_entry.configure(foreground="gray")

    def _search_changed(self, _event=None):
        if self._search_after is not None:
            self.root.after_cancel(self._search_after)
        self._search_after = self.root.after(150, self.apply_filter)

    # ----- data -----

    def _on_drop(self, paths):
        try:
            files = []
            for path in paths:
                if Path(path).is_dir():
                    files.extend(str(p) for p in sorted(Path(path).glob("*.vcf")))
                    files.extend(str(p) for p in sorted(Path(path).glob("*.vcard")))
                elif Path(path).suffix.lower() in (".vcf", ".vcard"):
                    files.append(path)
            if files:
                self.load_files(files)
            elif paths:
                self._set_status("Drop ignored: no .vcf files")
        except Exception as exc:
            self._set_status(f"Drop failed: {exc}")

    def _dialog_dir(self):
        last = self.state.get("last_dir", "")
        return last if last and Path(last).is_dir() else None

    def _remember_dir(self, path):
        self._save_state(last_dir=str(Path(path).parent))

    def _save_state(self, recent=None, last_dir=None):
        if recent is None:
            recent = self.state.get("recent", [])
        if last_dir is None:
            last_dir = self.state.get("last_dir", "")
        self.state = {"recent": recent, "last_dir": last_dir}
        save_state(recent, last_dir)

    def _rebuild_recent(self):
        menu = self.recent_menu
        menu.delete(0, tk.END)
        recent = [p for p in self.state.get("recent", [])[:MAX_RECENT]
                  if Path(p).is_file()]
        if not recent:
            menu.add_command(label="(Empty)", state=tk.DISABLED)
            return
        for path in recent:
            menu.add_command(label=path,
                             command=lambda p=path: self.load_files([p]))

    def _open_dialog(self):
        paths = filedialog.askopenfilenames(
            title="Open vCard file",
            initialdir=self._dialog_dir(),
            filetypes=[("vCard", "*.vcf *.vcard"), ("All files", "*.*")])
        if paths:
            self.load_files(paths)

    def load_file(self, path):
        self.load_files([path])

    def load_files(self, paths):
        paths = [str(p) for p in paths]
        contacts, failed, problems = [], [], []
        for path in paths:
            try:
                file_contacts, file_issues = parse_file_with_issues(path)
            except OSError:
                failed.append(Path(path).name)
                continue
            contacts.extend(file_contacts)
            problems.extend(file_issues)
        if failed:
            messagebox.showerror("Open failed",
                                 "Could not read:\n" + "\n".join(failed))
            if not contacts:
                return
        self.contacts = contacts
        self.current_files = paths
        self.selected = None
        self.apply_filter()
        fresh = [p for p in paths if Path(p).is_file()]
        recent = fresh + [p for p in self.state.get("recent", []) if p not in fresh]
        self._save_state(recent[:MAX_RECENT],
                         str(Path(paths[0]).parent) if paths else "")
        self._rebuild_recent()
        if not failed and problems:
            loaded = len(contacts)
            intro = (f"Loaded {loaded} contact(s), but found "
                     f"{len(problems)} problem(s):" if contacts else
                     "No usable contacts found. Problems:")
            messagebox.showerror("Problems in vCard file",
                                 intro + "\n\n" + self._format_problems(problems))
        elif not failed and not contacts:
            messagebox.showinfo(
                "No contacts",
                f"No vCards found in {self._source_label() or 'file'}.\n\n"
                "A contact needs BEGIN:VCARD … END:VCARD lines around it.")

    def _format_problems(self, problems):
        lines = []
        for issue in problems[:12]:
            where = Path(issue.source).name if issue.source else "file"
            lines.append(f"{where} line {issue.line}: {issue.problem}\n"
                         f"Fix: {issue.fix}")
        if len(problems) > 12:
            lines.append(f"…and {len(problems) - 12} more.")
        return "\n\n".join(lines)

    def _reload(self):
        if self.current_files:
            self.load_files(self.current_files)
        else:
            self._open_dialog()

    def _source_label(self):
        names = [Path(p).name for p in self.current_files]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return f"{names[0]} +{len(names) - 1}"

    def apply_filter(self):
        self.filtered = sort_contacts(
            filter_contacts(self.contacts, self._search_text(), self.type_var.get()),
            self.sort_var.get())
        self._render_list()

    @staticmethod
    def _iid(contact):
        return f"{contact.display_name}\x00{id(contact)}"

    def _render_list(self):
        self.tree.delete(*self.tree.get_children())
        for index, contact in enumerate(self.filtered):
            tags = ("stripe",) if index % 2 else ()
            self.tree.insert("", tk.END, iid=self._iid(contact),
                             text=contact.display_name or "(No name)",
                             values=(contact.subtitle(),), tags=tags)
        base = self._source_label() or "contacts"
        total = len(self.contacts)
        shown = len(self.filtered)
        if total:
            if shown == total:
                self._set_status(f"{total} contacts — {base}")
            else:
                self._set_status(f"{shown} of {total} — {base}")
            self.root.title(f"{base} — vCard Reader")
        else:
            self._set_status("No file")
            self.root.title("vCard Reader")
        children = self.tree.get_children()
        keep = None
        if self.selected is not None:
            iid = self._iid(self.selected)
            if iid in children:
                keep = iid
        if keep is None and children:
            keep = children[0]
        if keep is None:
            self.selected = None
            self._show_empty()
            self._set_status(right="")
            self._update_action_states()
        else:
            self._select_iid(keep)

    def _update_action_states(self):
        has_file = bool(self.current_files)
        has_selection = self.selected is not None
        reload_state = tk.NORMAL if has_file else tk.DISABLED
        sel_state = tk.NORMAL if has_selection else tk.DISABLED
        self.reload_btn.config(state=reload_state)
        self.export_btn.config(state=sel_state)
        self.copy_btn.config(state=sel_state)
        self.file_menu.entryconfig("Reload", state=reload_state)
        self.file_menu.entryconfig("Export selected…", state=sel_state)
        self.file_menu.entryconfig(
            "Export all…", state=tk.NORMAL if self.filtered else tk.DISABLED)
        self.edit_menu.entryconfig("Copy details", state=sel_state)
        self.edit_menu.entryconfig("Copy as vCard", state=sel_state)
        self.edit_menu.entryconfig("Copy phone", state=sel_state)
        self.edit_menu.entryconfig("Copy email", state=sel_state)

    @staticmethod
    def _counts_text(contact):
        bits = []
        n = len(contact.phones)
        if n:
            bits.append(f"{n} phone" if n == 1 else f"{n} phones")
        n = len(contact.emails)
        if n:
            bits.append(f"{n} email" if n == 1 else f"{n} emails")
        if not bits:
            return contact.display_name
        return f"{contact.display_name} · {' · '.join(bits)}"

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        for contact in self.filtered:
            if self._iid(contact) == iid:
                self.selected = contact
                self._show_details(contact)
                self._set_status(right=self._counts_text(contact))
                self._update_action_states()
                return

    def _select_iid(self, iid):
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        # Update state directly: the <<TreeviewSelect>> event only fires
        # once the event loop runs (see _render_list).
        self._on_select()

    def _on_list_drag(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self._select_iid(row)
        self._drag_autoscroll(event)

    def _cancel_drag_scroll(self, _event=None):
        job, self._drag_scroll_job = self._drag_scroll_job, None
        if job is not None:
            try:
                self.tree.after_cancel(job)
            except Exception:
                pass

    def _drag_autoscroll(self, event=None):
        self._cancel_drag_scroll()
        if event is None:
            try:
                y = self.tree.winfo_pointery() - self.tree.winfo_rooty()
            except Exception:
                return
        else:
            y = event.y
        height = self.tree.winfo_height()
        margin = 24
        if y < margin:
            delta = -1
        elif y > height - margin:
            delta = 1
        else:
            return
        self.tree.yview_scroll(delta, "units")
        row = self.tree.identify_row(y)
        if row and row not in self.tree.selection():
            self._select_iid(row)
        # Pointer held in the zone: keep scrolling until release.
        self._drag_scroll_job = self.tree.after(50, self._drag_autoscroll)

    def _on_list_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self._select_iid(row)
        menu = tk.Menu(self.root, tearoff=0)
        contact = self.selected
        if contact is not None:
            menu.add_command(label="Copy details", command=self._copy_details)
            menu.add_command(label="Copy as vCard", command=self._copy_vcard)
            if len(contact.phones) == 1:
                menu.add_command(label=f"Copy {contact.phones[0][1]}",
                                 command=self._copy_phone)
            elif contact.phones:
                phones = tk.Menu(menu, tearoff=0)
                menu.add_cascade(label="Copy phone", menu=phones)
                for label, number in contact.phones:
                    text = f"{label}: {number}" if label else number
                    phones.add_command(
                        label=text,
                        command=lambda n=number: self._copy_value(n))
            if len(contact.emails) == 1:
                menu.add_command(label=f"Copy {contact.emails[0][1]}",
                                 command=self._copy_email)
            elif contact.emails:
                emails = tk.Menu(menu, tearoff=0)
                menu.add_cascade(label="Copy email", menu=emails)
                for label, address in contact.emails:
                    text = f"{label}: {address}" if label else address
                    emails.add_command(
                        label=text,
                        command=lambda a=address: self._copy_value(a))
            menu.add_separator()
            menu.add_command(label="Export selected…", command=self._export_selected)
            menu.add_separator()
        else:
            menu.add_command(label="Copy details", command=self._copy_details,
                             state=tk.DISABLED)
            menu.add_separator()
        menu.add_command(label="Select all", command=self._select_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _select_all(self):
        self.tree.selection_set(self.tree.get_children())

    # ----- details -----

    def _write(self, text="", tag=None):
        self.details.insert(tk.END, text, tag or ())

    def _show_empty(self):
        self.details.configure(state=tk.NORMAL)
        self.details.delete("1.0", tk.END)
        if self.contacts:
            self._write("No matches. Try a different search or filter.", "dim")
        else:
            self._write("Open a .vcf file to begin.", "dim")
        self.details.configure(state=tk.DISABLED)

    def _copy_tag(self, value, url=False):
        tag = f"copy{self._copy_seq}"
        self._copy_seq += 1
        # Text tags have no -cursor option; switch the widget cursor on hover.
        self.details.tag_bind(tag, "<Enter>",
                              lambda e: self.details.configure(cursor="hand2"))
        self.details.tag_bind(tag, "<Leave>",
                              lambda e: self.details.configure(cursor=""))
        if url:
            self.details.tag_bind(tag, "<Button-1>",
                                  lambda e, u=value: webbrowser.open(u))
        else:
            self.details.tag_bind(
                tag, "<Button-1>",
                lambda e, v=value: (self._copy_value(v),
                                    self._set_status(f"Copied {v}")))
        return tag

    def _show_details(self, contact):
        self.details.configure(state=tk.NORMAL)
        self.details.delete("1.0", tk.END)
        self._copy_seq = 0
        self._write(contact.display_name or "(No name)", "h1")
        self._write("\n")
        sub = " — ".join(p for p in (contact.title, contact.organisation) if p)
        if sub:
            self._write(sub + "\n", "sub")
        self._write("\n")

        def section(title, rows, copy=False):
            if not rows:
                return
            self._write(title + "\n", "section")
            for label, value in rows:
                if label:
                    self._write(label + "  ", "label")
                tag = self._copy_tag(value) if copy else None
                for i, line in enumerate(value.split("\n")):
                    if i:
                        self._write("\n" + " " * 2, "label")
                    self._write(line, ("value", tag) if tag else "value")
                self._write("\n")

        section("Phone", contact.phones, copy=True)
        section("Email", contact.emails, copy=True)
        section("Address", contact.addresses)
        if contact.urls:
            self._write("Web\n", "section")
            for url in contact.urls:
                self._write(url, ("value", self._copy_tag(url, url=True)))
                self._write("\n", "value")
        if contact.birthday:
            self._write("Birthday\n", "section")
            self._write(contact.birthday + "\n", "value")
        if contact.note:
            self._write("Note\n", "section")
            self._write(contact.note + "\n", "value")
        source_bits = []
        if contact.source:
            source_bits.append(Path(contact.source).name)
        if contact.version:
            source_bits.append(f"vCard {contact.version}")
        if source_bits:
            self._write("\n" + " · ".join(source_bits), "dim")
        self.details.configure(state=tk.DISABLED)

    # ----- actions -----

    def _on_ctrl_a(self, event=None):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._select_all()
        return "break"

    def _on_ctrl_c(self, event=None):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._copy_details()
        return "break"

    def _on_ctrl_f(self, event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    def _search_clear(self, event=None):
        self.search_var.set("")
        self.apply_filter()
        self.tree.focus_set()
        return "break"

    def _on_enter(self, _event=None):
        self._copy_details()

    def _zoom(self, step):
        size = min(20, max(8, self.detail_font.cget("size") + step))
        self.detail_font.configure(size=size)

    def _export_all(self):
        if not self.filtered:
            messagebox.showinfo("Export", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export contacts",
            initialdir=self._dialog_dir(),
            defaultextension=".vcf",
            filetypes=[("vCard", "*.vcf")],
            initialfile="contacts.vcf")
        if not path:
            return
        try:
            Path(path).write_text(
                "\n".join(c.raw for c in self.filtered) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        self._remember_dir(path)
        self._set_status(f"Exported {len(self.filtered)} contacts")

    def _export_selected(self):
        if self.selected is None:
            messagebox.showinfo("Export", "Select a contact first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export contact",
            initialdir=self._dialog_dir(),
            defaultextension=".vcf",
            filetypes=[("vCard", "*.vcf")],
            initialfile=f"{self.selected.display_name or 'contact'}.vcf")
        if not path:
            return
        try:
            Path(path).write_text(self.selected.raw + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        self._remember_dir(path)
        self._set_status(f"Exported {self.selected.display_name}")

    def _copy_details(self):
        if self.selected is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.selected.to_text())
        self._set_status(f"Copied {self.selected.display_name}")

    def _copy_vcard(self):
        if self.selected is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.selected.raw + "\n")
        self._set_status(f"Copied vCard for {self.selected.display_name}")

    def _copy_value(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def _copy_phone(self):
        if self.selected and self.selected.phones:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.selected.phones[0][1])

    def _copy_email(self):
        if self.selected and self.selected.emails:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.selected.emails[0][1])

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "vCard Reader\nSimple .vcf viewer built with tkinter.\n\nBy theonlyasdk")

    def _on_closing(self):
        target = getattr(self.root, "_file_drop_target", None)
        if target is not None:
            try:
                target.close()
            except Exception:
                pass
        try:
            if self._search_after is not None:
                self.root.after_cancel(self._search_after)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
