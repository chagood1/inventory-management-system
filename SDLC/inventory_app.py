'''
Clay Hagood
CIS 3365 
Inventory and Supplier Management System
05/11/2025
'''

import tkinter as tk                             # GUI framework for window and widgets
from tkinter import ttk, messagebox              # Themed widgets and message dialog
import sqlite3                                    # SQLite database connectivity
import re                                         # Regular expressions for input validation
from datetime import datetime                    # For parsing and formatting dates
from datetime import datetime as _dt             # Alias for SQLite date adapter

# Date Adapter for SQLite
# This adapter allows us to store Python datetime objects directly as ISO strings in SQLite.
def adapt_date(date):
    if isinstance(date, _dt):
        return date.strftime('%Y-%m-%d')
    return date

sqlite3.register_adapter(_dt, adapt_date)         # Tell SQLite how to store datetime objects

# Database Setup 
conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

# Create supplier table
cursor.execute('''
CREATE TABLE IF NOT EXISTS supplier (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    account_number TEXT
)''')

# Create inventory table with foreign key to supplier
cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    category TEXT,
    supplier_id TEXT,
    expiration_date DATE,
    FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id)
)''')
conn.commit()

# Create category lookup table
cursor.execute('''
CREATE TABLE IF NOT EXISTS category (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cat_name TEXT UNIQUE
)''')

# Create transaction history for audit trail of stock changes
cursor.execute('''
CREATE TABLE IF NOT EXISTS txn_history (
    txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    change_qty INTEGER,
    txn_date DATE DEFAULT CURRENT_DATE,
    FOREIGN KEY (item_id) REFERENCES inventory(item_id)
)''')

# Create user table for future login/role features
cursor.execute('''
CREATE TABLE IF NOT EXISTS user (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    role TEXT
)''')

        #Main class/Initialize the GUI, database cursor, and set up event handlers.
class InventoryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventory Management System")
        self.cursor = conn.cursor()
        self.mode = 'inventory'    
        self.low_win = None         
        self.exp_win = None         

        self.root.resizable(True, True)  
        self.create_widgets()           
        self.load_data()                

        # Geometry Persistence 
        # Save window size/position on every resize or move
        self.root.update_idletasks()
        self.current_geometry = self.root.geometry()
        self.root.bind('<Configure>', self._track_geometry)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        
        #Initialize GUI styles and configure Treeview header appearance.
    def create_widgets(self):
        style = ttk.Style()              
        style.theme_use('clam')  
        style.configure('Treeview.Heading',
                        background='#4a4a4a', 
                        foreground='white',
                        relief='flat')
        style.map('Treeview.Heading',
                background=[('active','#4a4a4a'),('pressed','#4a4a4a')],
                foreground=[('active','white'),('pressed','white')])

        # Top toolbar frame
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.X, pady=5)

        # Buttons: Add, Delete, Low Stock Report, Expiring Soon Report
        for text, cmd in [
            ('Add', self.add_record),
            ('Delete', self.delete_record),
            ('Low Quantity Report', self.view_low_quantity),
            ('Expiring Soon Report', self.view_expiring_soon)
        ]:
            tk.Button(frame, text=text, command=cmd).pack(side=tk.LEFT, padx=5)

        # Search entry and button
        self.search_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.search_var).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text='Search', command=self.search_records).pack(side=tk.LEFT, padx=5)

        # Switch view buttons for Inventory vs. Suppliers
        tk.Button(frame, text='View Inventory', command=self.switch_to_inventory).pack(side=tk.RIGHT, padx=5)
        tk.Button(frame, text='View Suppliers', command=self.switch_to_supplier).pack(side=tk.RIGHT, padx=5)

        # Main Treeview for data display
        self.tree = ttk.Treeview(self.root, show='headings')
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._bind_tree(self.tree)

        # Status label at the bottom for hints and messages
        self.status_label = tk.Label(self.root, text='', anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=10, pady=(0,5))
        
        # Attach event bindings for editing, hover effects, and styling.
    def _bind_tree(self, tree):
        tree.bind('<Double-1>', self.edit_record)
        tree.bind('<Motion>', self.on_tree_motion)
        tree.bind('<Leave>', self.clear_status)
        tree.tag_configure('evenrow', background='#ffffff')
        tree.tag_configure('oddrow', background='#f0f0ff')
        tree.tag_configure('hover', background='#d0e0ff')
        
        # Update saved window geometry and adjust column widths.
    def _track_geometry(self, event=None):
        self.current_geometry = self.root.geometry()
        self.on_resize()
        
        # Highlight row under cursor and show 'Double-click to edit' hint.
    def on_tree_motion(self, event):
        tree = event.widget
        row = tree.identify_row(event.y)
        for item in tree.get_children():
            tag = 'evenrow' if tree.index(item) % 2 == 0 else 'oddrow'
            tree.item(item, tags=(tag,))
        self.clear_status()
        if row:
            tree.item(row, tags=('hover',))
            self.status_label.config(text='Double-click to edit')
            if hasattr(self, '_status_after'):
                self.root.after_cancel(self._status_after)
            self._status_after = self.root.after(2000, self.clear_status)
            
        # Clear the status label immediately.
    def clear_status(self, event=None):
        if hasattr(self, '_status_after'):
            self.root.after_cancel(self._status_after)
            del self._status_after
        self.status_label.config(text='')
        
        # Temporarily display a message in the status bar.
    def flash_message(self, msg, duration=3000):
        self.status_label.config(text=msg)
        self.root.after(duration, lambda: self.status_label.config(text=''))
        
        # Evenly distribute column widths when the window is resized.
    def on_resize(self, event=None):
        cols = self.tree['columns']
        if not cols:
            return
        total_width = self.tree.winfo_width()
        col_width = max(int(total_width / len(cols)) - 1, 20)
        for c in cols:
            self.tree.column(c, width=col_width)
            
        # Switch view to inventory table and reload data.
    def switch_to_inventory(self):
        self.mode = 'inventory'
        self.load_data()
        self.root.geometry(self.current_geometry)
        
        # Switch view to supplier table and reload data.
    def switch_to_supplier(self):
        self.mode = 'supplier'
        self.load_data()
        self.root.geometry(self.current_geometry)
        
        # Load data from the database into the Treeview.
    def load_data(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        if self.mode == 'inventory':
            cols = ('ID','Item Name','Quantity','Category','Supplier','Expiration Date')
            sql = 'SELECT * FROM inventory'
        else:
            cols = ('ID','Name','Phone','Email','Account Number')
            sql = 'SELECT * FROM supplier'
        self.tree.config(columns=cols)
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor=tk.CENTER)
        self.cursor.execute(sql)
        for idx, row in enumerate(self.cursor.fetchall()):
            if self.mode == 'inventory':
                try:
                    exp = datetime.strptime(row[5], '%Y-%m-%d').strftime('%m/%d/%Y')
                except:
                    exp = row[5]
                vals = (row[0], row[1], row[2], row[3], row[4], exp)
            else:
                vals = row
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            self.tree.insert('', tk.END, values=vals, tags=(tag,))
        self.on_resize()

        # modals for adding and editing records
    def add_record(self):
        self.edit_window(new=True)
        
    def edit_record(self, event):
        sel = event.widget.focus()
        if sel:
            self.edit_window(values=event.widget.item(sel, 'values'))
            
        #Prompt for confirmation, then delete the selected record.
    def delete_record(self):
        sel = self.tree.focus()
        if not sel:
            messagebox.showwarning('Warning', 'Select a record to delete')
            return
        if messagebox.askyesno('Confirm', 'Delete this record?'):
            v = self.tree.item(sel, 'values')
            tbl = 'inventory' if self.mode == 'inventory' else 'supplier'
            col = 'item_id' if tbl == 'inventory' else 'supplier_id'
            self.cursor.execute(f'DELETE FROM {tbl} WHERE {col}=?', (v[0],))
            conn.commit()
            self.load_data()
            self.flash_message('Record deleted.')
            
        #Create a modal window for adding or editing a record."
    def edit_window(self, new=False, values=None):
        win = tk.Toplevel(self.root)
        win.transient(self.root)
        win.grab_set() 
        win.title('Add' if new else 'Edit')
        win.update_idletasks()
        x, y = self.root.winfo_rootx()+30, self.root.winfo_rooty()+30
        win.geometry(f"+{x}+{y}")

        # Fields differ by mode
        fields = (['Item Name','Quantity','Category','Supplier','Expiration Date (MM/DD/YYYY)']
                if self.mode == 'inventory'
                else ['Supplier ID','Name','Phone','Email','Account Number'])
        entries = []

        # Build form fields
        for i, lab in enumerate(fields):
            tk.Label(win, text=lab).grid(row=i, column=0, sticky=tk.W, padx=10, pady=5)
            e = tk.Entry(win)
            e.grid(row=i, column=1, padx=10, pady=5)
            if values:
                idx = i if new else i + (0 if self.mode == 'supplier' else 1)
                e.insert(0, values[idx])
            entries.append(e)

        tk.Button(win, text='Save',
                command=lambda: self.save(new, values, entries, win)
                ).grid(row=len(fields), column=0, columnspan=2, pady=10)
        
        # Validate input fields and INSERT or UPDATE the database.
    def save(self, new, values, entries, win):
        vals = [e.get().strip() for e in entries]
        
        # Phone number and email format validation
        if self.mode == 'supplier':
            if not re.fullmatch(r'[\d-]{7,20}', vals[2]):
                messagebox.showerror('Invalid Phone', '7 to 20 digits or hyphens only')
                return
            if not re.fullmatch(r'[^@]+@[^@]+\.[^@]+', vals[3]):
                messagebox.showerror('Invalid Email', 'Enter valid email')
                return
            
        # Inventory validation
        if self.mode == 'inventory':
            if not vals[1].isdigit() or int(vals[1]) < 0:
                messagebox.showerror('Invalid Quantity', 'Non-negative integer required')
                return
            try:
                exp_date = datetime.strptime(vals[4], '%m/%d/%Y')
            except:
                messagebox.showerror('Invalid Date', 'Use MM/DD/YYYY')
                return
            
        # Prepare SQL for INSERT or UPDATE
        if self.mode == 'inventory':
            if new:
                sql = ('INSERT INTO inventory '
                    '(item_name,quantity,category,supplier_id,expiration_date) '
                    'VALUES (?,?,?,?,?)')
                params = (vals[0], int(vals[1]), vals[2], vals[3], exp_date)
            else:
                sql = ('UPDATE inventory SET item_name=?,quantity=?,category=?,'
                    'supplier_id=?,expiration_date=? WHERE item_id=?')
                params = (vals[0], int(vals[1]), vals[2], vals[3], exp_date, values[0])
        else:
            if new:
                sql = 'INSERT INTO supplier VALUES (?,?,?,?,?)'
                params = (vals[0], vals[1], vals[2], vals[3], vals[4])
            else:
                sql = ('UPDATE supplier SET supplier_name=?,phone=?,email=?,'
                    'account_number=? WHERE supplier_id=?')
                params = (*vals[1:], values[0])

        self.cursor.execute(sql, params)
        conn.commit()
        self.load_data()
        win.destroy()
        self.flash_message('Record ' + ('Added.' if new else 'Updated.'))
        
        # Filter main view based on input 
    def search_records(self):
        term = self.search_var.get().strip()
        if not term:
            return self.load_data()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        tbl = 'inventory' if self.mode == 'inventory' else 'supplier'
        fld = 'item_name' if self.mode == 'inventory' else 'supplier_name'
        
        # Partial match Search Feature 
        self.cursor.execute(f"SELECT * FROM {tbl} WHERE {fld} LIKE ?", ('%'+term+'%',))
        for idx, r in enumerate(self.cursor.fetchall()):
            if self.mode == 'inventory':
                try:
                    exp = datetime.strptime(r[5], '%Y-%m-%d').strftime('%m/%d/%Y')
                except:
                    exp = r[5]
                vals = (r[0], r[1], r[2], r[3], r[4], exp)
            else:
                vals = r
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            self.tree.insert('', tk.END, values=vals, tags=(tag,))
            
            # Execute the low quantity query (items with quantity <=10)
    def view_low_quantity(self):
        if self.low_win and self.low_win.winfo_exists():
            self.low_win.lift()
            return
        self.low_win = tk.Toplevel(self.root)
        self.low_win.transient(self.root)
        self.low_win.title('Low Stock Report')
        tk.Label(self.low_win, text='Low Stock Report', font=('Arial', 14, 'bold')).pack(pady=5)
        self.low_win.update_idletasks()
        x, y = self.root.winfo_rootx()+30, self.root.winfo_rooty()+30
        self.low_win.geometry(f"+{x}+{y}")
        tree = ttk.Treeview(self.low_win, columns=('ID','Name','Qty'), show='headings')
        for col in ('ID','Name','Qty'):
            tree.heading(col, text=col)
            tree.column(col, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.low_win.protocol('WM_DELETE_WINDOW', self.low_win.destroy)
        self.cursor.execute('SELECT item_id, item_name, quantity FROM inventory WHERE quantity <= ?', (10,))
        for idx, row in enumerate(self.cursor.fetchall()):
            tag = 'evenrow' if idx % 2==0 else 'oddrow'
            tree.insert('', tk.END, values=row, tags=(tag,))
            
        # Execute the expiring soon query (items with expiration_date <= today+30 days)
    def view_expiring_soon(self):
        if self.exp_win and self.exp_win.winfo_exists():
            self.exp_win.lift()
            return
        self.exp_win = tk.Toplevel(self.root)
        self.exp_win.transient(self.root)
        self.exp_win.title('Expiring Soon Report')
        tk.Label(self.exp_win, text='Expiring Soon Report', font=('Arial', 14, 'bold')).pack(pady=5)
        self.exp_win.update_idletasks()
        if hasattr(self, 'low_win') and self.low_win and self.low_win.winfo_exists():
            lx, ly = self.low_win.winfo_rootx(), self.low_win.winfo_rooty()
            lh = self.low_win.winfo_height()
            x, y = lx, ly + lh + 10
        else:
            x, y = self.root.winfo_rootx()+30, self.root.winfo_rooty()+30
        self.exp_win.geometry(f"+{x}+{y}")
        tree = ttk.Treeview(self.exp_win, columns=('ID','Name','Exp Date'), show='headings')
        for col in ('ID','Name','Exp Date'):
            tree.heading(col, text=col)
            tree.column(col, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.exp_win.protocol('WM_DELETE_WINDOW', self.exp_win.destroy)
        
        self.cursor.execute(
            "SELECT item_id, item_name, expiration_date FROM inventory "
            "WHERE DATE(expiration_date) <= DATE('now','+30 days')"
        )
        for idx, row in enumerate(self.cursor.fetchall()):
            try:
                exp = datetime.strptime(row[2], '%Y-%m-%d').strftime('%m/%d/%Y')
            except:
                exp = row[2]
            tag = 'evenrow' if idx % 2==0 else 'oddrow'
            tree.insert('', tk.END, values=(row[0], row[1], exp), tags=(tag,))

    def on_close(self):
        """Commit changes, close DB connection, and destroy the main window."""
        conn.commit()
        conn.close()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    InventoryApp(root)
    root.mainloop()
