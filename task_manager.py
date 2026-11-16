import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

DB = "tasks.db"

class TaskManager:
    def __init__(self, root):
        self.root = root
        self.root.title("مدیریت کارها")
        self.root.geometry("1050x680")
        self.root.minsize(850, 550)
        self.root.configure(bg="#101522")
        self.db = sqlite3.connect(DB)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, details TEXT DEFAULT '',
                priority TEXT NOT NULL, due TEXT DEFAULT '',
                done INTEGER DEFAULT 0, created TEXT NOT NULL
            )
        """)
        self.db.commit()
        self.bg, self.panel, self.panel2 = "#101522", "#192235", "#26334a"
        self.fg, self.muted, self.accent = "#f3f5fb", "#aab6ca", "#8878ff"
        self.setup_style()
        self.build()
        self.refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview", background=self.panel2, foreground=self.fg,
                    fieldbackground=self.panel2, rowheight=34, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=self.panel, foreground=self.fg,
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", self.accent)])

    def label(self, parent, text, size=10, color=None, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=color or self.fg,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def build(self):
        header = tk.Frame(self.root, bg=self.bg)
        header.pack(fill="x", padx=22, pady=18)
        self.label(header, "مدیریت کارها", 24, bold=True).pack(side="right")
        self.label(header, "برنامه‌ریزی کن، انجام بده، پیشرفتت رو ببین",
                   10, self.muted).pack(side="left", pady=12)

        stats = tk.Frame(self.root, bg=self.bg)
        stats.pack(fill="x", padx=18)
        self.stat = {}
        for key, caption in [("all", "همه کارها"), ("todo", "در انتظار"),
                             ("done", "انجام‌شده"), ("rate", "پیشرفت")]:
            card = tk.Frame(stats, bg=self.panel, padx=16, pady=12)
            card.pack(side="right", expand=True, fill="x", padx=5)
            self.label(card, caption, 10, self.muted).pack(anchor="e")
            self.stat[key] = self.label(card, "0", 22, bold=True)
            self.stat[key].pack(anchor="e", pady=(4, 0))

        body = tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True, padx=22, pady=16)

        form = tk.Frame(body, bg=self.panel, padx=15, pady=15, width=285)
        form.pack(side="right", fill="y", padx=(0, 12))
        form.pack_propagate(False)
        self.label(form, "افزودن / ویرایش کار", 14, bold=True).pack(anchor="e", pady=(0, 10))
        self.title_var, self.due_var = tk.StringVar(), tk.StringVar()
        self.priority_var = tk.StringVar(value="متوسط")
        self.field(form, "عنوان کار", self.title_var)
        self.field(form, "تاریخ سررسید (YYYY-MM-DD)", self.due_var)
        self.label(form, "اولویت", 9, self.muted).pack(anchor="e", pady=(10, 4))
        ttk.Combobox(form, textvariable=self.priority_var, values=["کم", "متوسط", "زیاد"],
                      state="readonly", justify="right").pack(fill="x", ipady=5)
        self.label(form, "توضیحات", 9, self.muted).pack(anchor="e", pady=(10, 4))
        self.details = tk.Text(form, height=6, bg=self.panel2, fg=self.fg,
                               insertbackground="white", relief="flat", wrap="word")
        self.details.pack(fill="x")
        self.selected_id = None
        self.save_btn = self.btn(form, "＋ افزودن کار", self.save, self.accent)
        self.save_btn.pack(fill="x", pady=(15, 7))
        self.btn(form, "پاک کردن فرم", self.clear, self.panel2).pack(fill="x")

        area = tk.Frame(body, bg=self.panel, padx=13, pady=13)
        area.pack(side="left", fill="both", expand=True)
        top = tk.Frame(area, bg=self.panel)
        top.pack(fill="x", pady=(0, 10))
        self.label(top, "فهرست کارها", 14, bold=True).pack(side="right")
        self.search_var = tk.StringVar()
        search = tk.Entry(top, textvariable=self.search_var, justify="right",
                          bg=self.panel2, fg=self.fg, insertbackground="white",
                          relief="flat", font=("Segoe UI", 10), width=22)
        search.pack(side="left", ipady=7)
        search.bind("<KeyRelease>", lambda e: self.refresh())

        filters = tk.Frame(area, bg=self.panel)
        filters.pack(fill="x", pady=(0, 9))
        self.filter_var = tk.StringVar(value="همه")
        for value in ["همه", "در انتظار", "انجام‌شده"]:
            tk.Radiobutton(filters, text=value, value=value, variable=self.filter_var,
                           command=self.refresh, bg=self.panel, fg=self.muted,
                           selectcolor=self.panel2, activebackground=self.panel,
                           activeforeground=self.fg).pack(side="right", padx=5)

        cols = ("id", "title", "priority", "due", "status")
        self.tree = ttk.Treeview(area, columns=cols, show="headings")
        for col, heading, width in [
            ("id", "شناسه", 55), ("title", "عنوان کار", 250),
            ("priority", "اولویت", 85), ("due", "سررسید", 110),
            ("status", "وضعیت", 95)
        ]:
            self.tree.heading(col, text=heading, anchor="center")
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected)

        actions = tk.Frame(area, bg=self.panel)
        actions.pack(fill="x", pady=(11, 0))
        self.btn(actions, "✓ انجام شد / بازگرداندن", self.toggle, "#28a879").pack(side="right", padx=4)
        self.btn(actions, "ویرایش", self.edit, self.accent).pack(side="right", padx=4)
        self.btn(actions, "حذف", self.delete, "#df526b").pack(side="right", padx=4)
        self.status = tk.StringVar(value="آماده")
        tk.Label(self.root, textvariable=self.status, anchor="e", bg=self.bg,
                 fg=self.muted, font=("Segoe UI", 9)).pack(fill="x", padx=25, pady=(0, 8))

    def field(self, parent, caption, var):
        self.label(parent, caption, 9, self.muted).pack(anchor="e", pady=(8, 4))
        tk.Entry(parent, textvariable=var, justify="right", bg=self.panel2,
                 fg=self.fg, insertbackground="white", relief="flat",
                 font=("Segoe UI", 10)).pack(fill="x", ipady=7)

    def btn(self, parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"),
                         padx=9, pady=8)

    def save(self):
        title = self.title_var.get().strip()
        details = self.details.get("1.0", "end").strip()
        priority, due = self.priority_var.get(), self.due_var.get().strip()
        if not title:
            messagebox.showwarning("عنوان لازم است", "عنوان کار را وارد کن.")
            return
        if due:
            try:
                datetime.strptime(due, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("تاریخ نامعتبر", "تاریخ را مانند 2026-12-25 وارد کن.")
                return
        if self.selected_id is None:
            self.db.execute("INSERT INTO tasks(title,details,priority,due,created) VALUES(?,?,?,?,?)",
                            (title, details, priority, due, datetime.now().isoformat(timespec="seconds")))
            msg = "کار جدید اضافه شد."
        else:
            self.db.execute("UPDATE tasks SET title=?,details=?,priority=?,due=? WHERE id=?",
                            (title, details, priority, due, self.selected_id))
            msg = "ویرایش ذخیره شد."
        self.db.commit()
        self.clear()
        self.refresh()
        self.status.set(msg)

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        term = "%" + self.search_var.get().strip() + "%"
        sql = "SELECT * FROM tasks WHERE (title LIKE ? OR details LIKE ?)"
        params = [term, term]
        if self.filter_var.get() == "در انتظار":
            sql += " AND done=0"
        elif self.filter_var.get() == "انجام‌شده":
            sql += " AND done=1"
        sql += """ ORDER BY CASE priority WHEN 'زیاد' THEN 1
                    WHEN 'متوسط' THEN 2 ELSE 3 END,
                    CASE WHEN due='' THEN 1 ELSE 0 END, due, id DESC"""
        for row in self.db.execute(sql, params):
            self.tree.insert("", "end", iid=str(row["id"]),
                values=(row["id"], row["title"], row["priority"],
                        row["due"] or "—", "انجام‌شده" if row["done"] else "در انتظار"))
        row = self.db.execute("SELECT COUNT(*) total, SUM(done) done FROM tasks").fetchone()
        total, done = row["total"] or 0, row["done"] or 0
        self.stat["all"].config(text=str(total))
        self.stat["todo"].config(text=str(total-done))
        self.stat["done"].config(text=str(done))
        self.stat["rate"].config(text=f"{round(done*100/total) if total else 0}%")

    def selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("انتخاب کار", "ابتدا یک کار را انتخاب کن.")
            return None
        return int(selection[0])

    def load_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        task_id = int(selection[0])
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row:
            self.selected_id = task_id
            self.title_var.set(row["title"])
            self.due_var.set(row["due"])
            self.priority_var.set(row["priority"])
            self.details.delete("1.0", "end")
            self.details.insert("1.0", row["details"])
            self.save_btn.config(text="ذخیره ویرایش")

    def edit(self):
        task_id = self.selected()
        if task_id is not None:
            self.load_selected()
            self.status.set(f"در حال ویرایش کار شماره {task_id}")

    def toggle(self):
        task_id = self.selected()
        if task_id is None:
            return
        row = self.db.execute("SELECT done FROM tasks WHERE id=?", (task_id,)).fetchone()
        self.db.execute("UPDATE tasks SET done=? WHERE id=?", (1-row["done"], task_id))
        self.db.commit()
        self.refresh()
        self.status.set("وضعیت کار تغییر کرد.")

    def delete(self):
        task_id = self.selected()
        if task_id is not None and messagebox.askyesno("تأیید حذف", "این کار حذف شود؟"):
            self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            self.db.commit()
            self.clear()
            self.refresh()
            self.status.set("کار حذف شد.")

    def clear(self):
        self.selected_id = None
        self.title_var.set("")
        self.due_var.set("")
        self.priority_var.set("متوسط")
        self.details.delete("1.0", "end")
        self.save_btn.config(text="＋ افزودن کار")
        for item in self.tree.selection():
            self.tree.selection_remove(item)

    def close(self):
        self.db.close()
        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    TaskManager(app_root)
    app_root.mainloop()
