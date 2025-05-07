# What Was That Shit?! (WWTS)

A configurable overlay and history saver for all images you may deal with, including fast screenshot functionality and even GIF playback.

## Features

- Monitors clipboard for images (PrintScreen or Ctrl+C but not really it looks at the file content but if I change this setting things break, yay.)
- Displays images in a moveable, resizable, transparency-adjustable overlay that is such a dirty little overlay you can resize it with the scroll-wheel 	and it will maintain aspect ratios no matter what.
- Images can be copied from files in explorer and even straight from web browsers and they will instantly enter the overlay if auto-refresh is enabled.
	GIFs will load still and can be right-clicked to play on a loop.
- System tray integration that mostly works, minimize and still utilize the overlay and core functions.
- Instant screenshot on double shift. Pressing double shift instantly grabs a portion of the screen around your mouse cursor (and saves it with history 	on!) which allows you to do all sorts of things like grab fast moving chats, game maps and probably naughty stuff.
- Dark/Light/Auto theme support but just use dark cause it's slightly prettier.
- Image history saving option, with history on you can easily find images from throughout your day.
- Only now realizing how goon-friendly most of this program is.

## Requirements

- Windows OS
- Python 3.9+
- Dependencies listed in requirements.txt
- There are Linux build scripts but fuck me if I would know if they work or not. Fuck you too, but in a nicer way.

## Installation

1. None, because we keep shit portable g'damnit. Settings/History stored with exe.

## Configuration

Settings are stored in a JSON file in the application directory and include:
- Always on top
- Clickthrough
- Auto-refresh
- Minimize on start-up
- Resize Behaviour
- History saving
- Opacity level
- Personal Insecurity

## Usage Tips

- Overlay has a fleshed out right click context menu, use it to manually refresh or play pause gifs.
- Double clicking the overlay will switch between no transparency and your chosen percentage.
- You can hide the overlay with the right click menu, the system tray and even the settings panel. 
	Turn Auto-Refresh off if you don't want it to pop up when it gets a new image. This could be useful if you have history saving on and just go ham 	on your meat treat beat.
- Save settings once you alter them, if they don't take effect, close and reopen afterwards. 