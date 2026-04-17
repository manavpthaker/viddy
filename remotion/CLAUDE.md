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
- **Caption size:** 64px (configured in brand.json)
- **Weight:** 800 for active word, 900 for highlight, 600 for inactive
- **Letter spacing:** -0.02em
- **Max words visible:** 3-4 at a time
- **Text color:** #FFFFFF (inactive: rgba(255,255,255,0.45))
- **Highlight color:** #7B9E87 (sage green accent)
- **Text stroke:** 6px solid black — heavy stroke for DOAC legibility at 1080p
- **Drop shadow:** 0 4px 0 rgba(0,0,0,0.5), 0 0 12px rgba(0,0,0,0.4)
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
- Base scale: 1.35 (this IS the tracking crop — fills frame on active speaker)
- Emphasis punch: additional 1.06x on top of base (total ~1.43x, which is intentional)
- Transition between speakers: 0.4s ease-in-out
- Note: "no zoom > 1.1x" anti-pattern refers to the emphasis *punch* delta, not total scale

## Progress Bar
- Position: top, inside safe zone (below 12% mark = 230px from top)
- Height: 3px
- Color: #7B9E87
- Background: rgba(255,255,255,0.1)

## Hook Overlay
- First 3 seconds (90 frames at 30fps) with fade in/out
- Most provocative line from the clip
- Position: 8% from top (safe zone)
- Font: DM Sans 64px, weight 800 (standalone size, not derived from caption size)
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
- NO emphasis punch greater than 1.1x (the delta, not total scale — should feel subtle)
- NO hard cuts on speaker switches (always ease transition)
