import asyncio
from contextlib import suppress
from dataclasses import dataclass
import signal
import tkinter as tk
from tkinter import ttk

from pulsectl import PulseIndexError
import pulsectl_asyncio

@dataclass
class Window:
    geometry: str
    root: tk.Tk | tk.Toplevel
    volume_label: ttk.Label
    progress_bar: ttk.Progressbar

class Gui:
    windows: list[Window]
    root: tk.Tk

    def __init__(self):
        self.windows = []

        root = tk.Tk()
        self.root = root

        s = ttk.Style()
        s.configure("TProgressbar", thickness=30,
                    troughcolor="#333333", background="#00ddff")
        s.configure("TFrame", background="black")
        s.configure("TLabel", background="black",
                    foreground="white", font=('Cascadia Mono', 12))

        secondary = tk.Toplevel()

        geom = (
            "+0+24",
            "+0+794"
        )

        for n, (win, g) in enumerate(zip((secondary, root), geom), 1):
            win.configure(background="black")
            win.wm_attributes("-type", "notification")
            win.wm_attributes("-topmost", True)
            win.overrideredirect(True)
            win.withdraw()

            frm = ttk.Frame(win, padding=8, style="TFrame")
            frm.grid()

            ttk.Label(frm, text="VOL").grid(column=0, row=0)
            progress_bar = ttk.Progressbar(frm, orient="vertical", style="TProgressbar")
            progress_bar.grid(column=0, row=1)
            volume_label = ttk.Label(frm)
            volume_label.grid(column=0, row=2)

            win.geometry(g)

            self.windows.append(Window(g, win, volume_label, progress_bar))

        root.update_idletasks()
        root.update()


    async def withdraw_timeout(self, duration: int):
        await asyncio.sleep(duration)
        for win in self.windows:
            win.root.withdraw()
            win.root.update_idletasks()
            win.root.update()

    async def loop(self, queue: asyncio.Queue):
        while True:
            withdraw = asyncio.create_task(self.withdraw_timeout(3))
            val = await queue.get()
            withdraw.cancel()

            for win in self.windows:
                win.root.deiconify()
                win.root.geometry(win.geometry)
                win.progress_bar["value"] = val * 100
                if val <= .999:
                    win.volume_label["text"] = "{:^3.0%}".format(val)
                else:
                    win.volume_label["text"] = "MAX"

                win.root.update_idletasks()
                win.root.update()


class App:
    volumes: asyncio.Queue

    def __init__(self):
        self.volumes = asyncio.Queue()

async def listen(queue: asyncio.Queue):
    async with pulsectl_asyncio.PulseAsync('volnotd') as pulse:
        last_volume = (await pulse.sink_default_get()).volume.value_flat
        async for event in pulse.subscribe_events('sink'):
            try:
                sink = await pulse.sink_default_get()
            except PulseIndexError:
                continue
            volume = sink.volume.value_flat

            if volume != last_volume:
                last_volume = volume
                await queue.put(volume)


def r():
    raise KeyboardInterrupt()


async def main():
    queue = asyncio.Queue()
    listen_task = asyncio.create_task(listen(queue))

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(sig, listen_task.cancel)
        loop.add_signal_handler(sig, r)

    gui = Gui()

    asyncio.create_task(gui.loop(queue))

    with suppress(asyncio.CancelledError):
        await listen_task

if __name__ == "__main__":
    asyncio.run(main())

