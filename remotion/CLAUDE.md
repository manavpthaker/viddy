# Viddy Remotion — Style Guide

This is the visual DNA for all rendered clips. Every component must follow these specs.

## Target Aesthetic
Diary of a CEO style shorts. Clean, high-end, minimal. Documentary feel.

## Resolution & Format
- Render at 1080x1920 (9:16 vertical) or 1080x1080 (square)
- FPS: 30
- Final codec: h264, CRF 18
- Preview: jpeg, quality 80

## Typography
- **Font:** DM Sans (fallback: Inter, Neue Haas Grotesk)
- **Caption size:** 56-64px
- **Weight:** 800-900 for active word, 600 for inactive
- **Letter spacing:** -0.02em
- **Max words visible:** 3-4 at a time
- **Text color:** #FFFFFF (inactive: rgba(255,255,255,0.5))
- **Highlight color:** #7B9E87 (sage green accent)
- **Text stroke:** 2px black stroke
- **Drop shadow:** 0 4px 0 rgba(0,0,0,0.4)
- **NO background box.** Use stroke + shadow for legibility.

## Caption Safe Zones
- TikTok/Reels UI eats bottom 18% and top 12%
- Anchor captions at ~60% vertical (1152px from top on 1920px canvas)
- NEVER place captions below 75% (1440px)
- Hook overlay: top safe zone, ~15% from top (288px)

## Motion
- Caption word entrance: spring animation (damping 12, stiffness 200)
- No fade-out on captions, just spring-in the next group
- Punch-in on speaker: 1.02-1.08x scale, subtle, over 8-12 frames
- Punch-in on emphasis: 1.04-1.06x, color shift on caption word
- All transitions: ease-in-out cubic, 0.3-0.5s

## Speaker Zoom
- Base scale: 1.0 (full frame visible, letterboxed to fit vertical)
- Speaker tracking crop: 1.3-1.4x to fill frame on active speaker
- Emphasis punch: additional 1.04x on top of tracking crop
- Transition between speakers: 0.4s ease-in-out

## Progress Bar
- Position: top, inside safe zone (below 12% mark = 230px from top)
- Height: 3px
- Color: #7B9E87
- Background: rgba(255,255,255,0.1)

## Hook Overlay
- First 30-45 frames (1-1.5s at 30fps)
- Most provocative line from the clip
- Position: 15% from top (safe zone)
- Font: same as captions, 48-52px
- Border-left accent: 4px #7B9E87
- Background: rgba(0,0,0,0.7) with 12px border-radius
- Enter: slide up 20px + fade in over 10 frames

## Colors
- Background (letterbox): #000000
- Caption text: #FFFFFF
- Caption highlight: #7B9E87
- Progress bar: #7B9E87
- All UI overlays: semi-transparent black (0.6-0.75 alpha)

## Anti-patterns
- NO bouncy/playful animations
- NO emoji overlays
- NO colored backgrounds behind captions (use stroke + shadow)
- NO text below 75% of frame height
- NO zoom greater than 1.1x (should feel subtle, not jarring)
- NO hard cuts on speaker switches (always ease transition)
