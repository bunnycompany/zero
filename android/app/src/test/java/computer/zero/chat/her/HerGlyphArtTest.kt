package computer.zero.chat.her

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HerGlyphArtTest {
    private fun lit(px: IntArray) = px.count { it > 0 }

    @Test fun frameIs25by25() {
        assertEquals(625, HerGlyphArt.frame("idle", false, false, 0f).size)
    }

    @Test fun asleepIsOneDimDot() {
        val px = HerGlyphArt.frame("asleep", true, true, 0.5f)
        assertEquals(1, lit(px))
        assertTrue(px[12 * 25 + 12] in 1..60)
    }

    @Test fun quietIsARingAndNothingInTheCentre() {
        val px = HerGlyphArt.frame("idle", false, false, 0.25f)
        assertTrue(lit(px) > 20)
        assertEquals(0, px[12 * 25 + 12])
    }

    @Test fun attentionFillsTheCentre() {
        val px = HerGlyphArt.frame("idle", false, true, 0f)
        assertEquals(255, px[12 * 25 + 12])
    }

    @Test fun questionAddsPixelsQuietLacks() {
        val a = HerGlyphArt.frame("idle", false, false, 0f)
        val b = HerGlyphArt.frame("idle", true, false, 0f)
        assertTrue(lit(b) > lit(a))
    }
}
