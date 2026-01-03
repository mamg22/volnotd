import asyncio
from contextlib import suppress
from dataclasses import dataclass
import signal
import tkinter as tk
from tkinter import ttk
from typing import NamedTuple

from pulsectl import PulseIndexError
import pulsectl_asyncio

@dataclass
class Window:
    geometry: str
    root: tk.Tk | tk.Toplevel
    state_label: ttk.Label
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
        s.configure("TProgressbar", thickness=24,
                    troughcolor="#333333", background="#00ddff")
        s.configure("TFrame", background="black")
        s.configure("TLabel", background="black",
                    foreground="white", font=('Cascadia Mono', 12))
        s.configure("Icon.TLabel", font=('Font Awesome 6 Free Solid', 12))

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

            state_label = ttk.Label(frm, style="Icon.TLabel")
            state_label.grid(column=0, row=0)
            progress_bar = ttk.Progressbar(frm, orient="vertical", style="TProgressbar")
            progress_bar.grid(column=0, row=1, pady=4)
            volume_label = ttk.Label(frm)
            volume_label.grid(column=0, row=2)

            win.geometry(g)

            self.windows.append(Window(g, win, state_label, volume_label, progress_bar))

        root.update_idletasks()
        root.update()


    async def withdraw_timeout(self, duration: int):
        await asyncio.sleep(duration)
        for win in self.windows:
            win.root.withdraw()
            win.root.update_idletasks()
            win.root.update()

    def update_window_state(self, win, state):
        win.state_label["text"] = "" if state.mute else ""
        win.progress_bar["value"] = state.volume * 100
        if state.volume <= .999:
            win.volume_label["text"] = "{:^3.0%}".format(state.volume)
        else:
            win.volume_label["text"] = "MAX"



    async def loop(self, queue: asyncio.Queue):
        while True:
            withdraw = asyncio.create_task(self.withdraw_timeout(3))
            state = await queue.get()
            withdraw.cancel()

            for win in self.windows:
                win.root.deiconify()
                win.root.geometry(win.geometry)

                self.update_window_state(win, state)

                win.root.update_idletasks()
                win.root.update()


class App:
    volumes: asyncio.Queue

    def __init__(self):
        self.volumes = asyncio.Queue()

class SinkState(NamedTuple):
    volume: float
    mute: bool

async def get_default_sink_state(pulse):
    sink = await pulse.sink_default_get()
    volume = sink.volume.value_flat
    mute = sink.mute == 1

    return SinkState(volume, mute)

async def listen(queue: asyncio.Queue):
    async with pulsectl_asyncio.PulseAsync('volnotd') as pulse:
        last_state = await get_default_sink_state(pulse)
        async for event in pulse.subscribe_events('sink'):
            try:
                state = await get_default_sink_state(pulse)
            except PulseIndexError:
                continue

            if state != last_state:
                await queue.put(state)

            last_state = state


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

