"""The Tk/ttk window runtime: build every widget kind from a spec, wire
the bindings and run the main loop."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from .actions import _apply_action, _interpolate


class DesktopRuntime:
    """Cross-platform desktop runtime layer for Windows/Linux.

    This runtime is intentionally backend-driven so Mellow's UI/event/state model
    stays stable even if the widget backend changes later. Current backend: Tk/ttk.
    """

    def __init__(self, spec: Dict[str, Any]):
        self.spec = dict(spec)
        self.state: Dict[str, Any] = dict(spec.get('state') or {})

    def launch(self) -> int:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title(str(self.spec.get('title', 'Mellow App')))
        root.geometry(f"{int(self.spec.get('width', 960))}x{int(self.spec.get('height', 640))}")
        refreshers: List[Callable[[], None]] = []

        def refresh_all() -> None:
            for fn in refreshers:
                fn()

        if self.spec.get('menus'):
            menu_bar = tk.Menu(root)
            for menu in self.spec['menus']:
                sub = tk.Menu(menu_bar, tearoff=0)
                for item in menu.get('items') or []:
                    if isinstance(item, dict):
                        label = str(item.get('label', 'Item'))
                        action = str(item.get('action', ''))
                        accelerator = item.get('accelerator')
                    else:
                        label = str(item)
                        action = f'print:{label}'
                        accelerator = None
                    sub.add_command(label=label, accelerator=accelerator or '', command=lambda a=action: _apply_action(a, root=root, state=self.state, refresh=refresh_all))
                menu_bar.add_cascade(label=str(menu.get('label', 'Menu')), menu=sub)
            root.config(menu=menu_bar)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        layout = self.spec.get('layout', 'vstack')
        horizontal = layout == 'hstack'

        for index, widget in enumerate(self.spec.get('widgets', [])):
            kind = widget.get('type')
            text = str(widget.get('text', ''))
            bind = widget.get('bind')
            pack_kwargs = {'pady': 6, 'anchor': 'w'}
            if horizontal:
                pack_kwargs['side'] = 'left'
                pack_kwargs['padx'] = 6
            if layout == 'grid':
                pack_kwargs = {}

            def _grid_pos(default_row: int) -> dict[str, int | str]:
                return {'row': int(widget.get('row', default_row)), 'column': int(widget.get('col', 0)), 'padx': 8, 'pady': 6, 'sticky': str(widget.get('sticky', 'w'))}

            if kind == 'label':
                label = ttk.Label(frame, text=_interpolate(text, self.state))
                if layout == 'grid':
                    label.grid(**_grid_pos(index))
                else:
                    label.pack(**pack_kwargs)
                refreshers.append(lambda lbl=label, template=text: lbl.config(text=_interpolate(template, self.state)))
            elif kind == 'button':
                action = str(widget.get('action', '') or '')
                btn = ttk.Button(frame, text=text, command=lambda a=action: _apply_action(a, root=root, state=self.state, refresh=refresh_all))
                if layout == 'grid':
                    btn.grid(**_grid_pos(index))
                else:
                    btn.pack(**pack_kwargs)
            elif kind == 'input':
                var = tk.StringVar(value=str(self.state.get(bind, text) if bind else text))
                entry = ttk.Entry(frame, textvariable=var)
                if layout == 'grid':
                    entry.grid(**_grid_pos(index))
                else:
                    entry.pack(fill='x', expand=not horizontal, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, v.get()))
                    refreshers.append(lambda key=bind, v=var: v.set(str(self.state.get(key, ''))))
            elif kind == 'textarea':
                box = tk.Text(frame, height=8)
                box.insert('1.0', str(self.state.get(bind, text) if bind else text))
                if layout == 'grid':
                    box.grid(**_grid_pos(index))
                else:
                    box.pack(fill='both', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    def _sync_text(event: Any, key: str = str(bind), widget_obj: Any = box) -> None:
                        self.state[key] = widget_obj.get('1.0', 'end-1c')
                    box.bind('<KeyRelease>', _sync_text)
                    refreshers.append(lambda key=bind, widget_obj=box: (widget_obj.delete('1.0', 'end'), widget_obj.insert('1.0', str(self.state.get(key, '')))))
            elif kind == 'checkbox':
                var = tk.BooleanVar(value=bool(self.state.get(bind, widget.get('default', False))))
                chk = ttk.Checkbutton(frame, text=text, variable=var)
                if layout == 'grid':
                    chk.grid(**_grid_pos(index))
                else:
                    chk.pack(**pack_kwargs)
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, bool(v.get())))
                    refreshers.append(lambda key=bind, v=var: v.set(bool(self.state.get(key, False))))
            elif kind == 'select':
                options = widget.get('options') or []
                if isinstance(options, str):
                    options = [options]
                var = tk.StringVar(value=str(self.state.get(bind, options[0] if options else text)))
                combo = ttk.Combobox(frame, values=list(options), textvariable=var, state='readonly')
                if layout == 'grid':
                    combo.grid(**_grid_pos(index))
                else:
                    combo.pack(fill='x', expand=not horizontal, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, v.get()))
                    refreshers.append(lambda key=bind, v=var: v.set(str(self.state.get(key, ''))))
            elif kind == 'slider':
                mn, mx = int(widget.get('min', 0)), int(widget.get('max', 100))
                var = tk.DoubleVar(value=float(self.state.get(bind, mn)))
                scale = ttk.Scale(frame, from_=mn, to=mx, variable=var)
                if layout == 'grid':
                    scale.grid(**_grid_pos(index))
                else:
                    scale.pack(fill='x', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    var.trace_add('write', lambda *_a, key=bind, v=var: self.state.__setitem__(key, int(float(v.get()))))
                    refreshers.append(lambda key=bind, v=var: v.set(float(self.state.get(key, mn))))
            elif kind == 'listbox':
                options = widget.get('options') or []
                if isinstance(options, str):
                    options = [options]
                listbox = tk.Listbox(frame, height=min(8, max(3, len(options))))
                for opt in options:
                    listbox.insert('end', str(opt))
                if layout == 'grid':
                    listbox.grid(**_grid_pos(index))
                else:
                    listbox.pack(fill='both', expand=True, **{k: v for k, v in pack_kwargs.items() if k != 'anchor'})
                if bind:
                    def _sync_list(_event: Any, key: str = str(bind), lb: Any = listbox) -> None:
                        sel = lb.curselection()
                        self.state[key] = lb.get(sel[0]) if sel else ''
                    listbox.bind('<<ListboxSelect>>', _sync_list)
            elif kind == 'spacer':
                spacer = ttk.Frame(frame, height=int(widget.get('size', 12)))
                if layout == 'grid':
                    spacer.grid(**_grid_pos(index))
                else:
                    spacer.pack(fill='x')

        root.mainloop()
        return 0


def launch_window(spec: Dict[str, Any]) -> int:
    return DesktopRuntime(spec).launch()
