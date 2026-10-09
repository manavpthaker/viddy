// Loads DM Sans for all compositions. Without this, every `fontFamily: 'DM Sans'`
// in the components silently falls back to a serif during render.
// loadFont() uses delayRender internally so frames wait until the font is ready.
import {loadFont} from '@remotion/google-fonts/DMSans';

export const {fontFamily: DM_SANS} = loadFont('normal', {
  weights: ['400', '500', '600', '700', '800', '900'],
  subsets: ['latin'],
});
