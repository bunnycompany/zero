package computer.zero.chat.her

/**
 * Her, as light on the back of a Nothing Phone (3): a 25x25 frame. Pure
 * functions over a state so the Glyph toy service stays tiny, and so this
 * can be unit-tested without a phone.
 *
 *   asleep     a single dim dot — she isn't running
 *   quiet      a soft ring, breathing with [phase]
 *   thinking   the ring, brighter, with a dot travelling around it
 *   question   the ring plus a small "?" — she has a question for you
 *   attention  a filled centre — something is there when you look
 */
object HerGlyphArt {
    const val N = 25
    private const val C = 12.0

    fun frame(state: String, question: Boolean, attention: Boolean, phase: Float): IntArray {
        val px = IntArray(N * N)
        fun set(x: Int, y: Int, v: Int) { if (x in 0 until N && y in 0 until N) px[y * N + x] = v.coerceIn(0, 255) }
        when {
            state == "asleep" -> set(12, 12, 40)
            else -> {
                val breathe = 0.55 + 0.45 * kotlin.math.sin(phase.toDouble() * 2 * Math.PI)
                val base = if (state == "thinking" || state == "executing") 255 else (150 * breathe).toInt() + 40
                ring(px, 8.5, base, ::set)
                if (state == "thinking" || state == "executing") {
                    val a = phase * 2 * Math.PI
                    set((C + 8.5 * kotlin.math.cos(a)).toInt(), (C + 8.5 * kotlin.math.sin(a)).toInt(), 255)
                }
                if (attention) disc(px, 3.2, 255, ::set)
                if (question) questionMark(::set)
            }
        }
        return px
    }

    private fun ring(px: IntArray, r: Double, v: Int, set: (Int, Int, Int) -> Unit) {
        for (y in 0 until N) for (x in 0 until N) {
            val d = kotlin.math.hypot(x - C, y - C)
            if (kotlin.math.abs(d - r) < 0.9) set(x, y, v)
        }
    }

    private fun disc(px: IntArray, r: Double, v: Int, set: (Int, Int, Int) -> Unit) {
        for (y in 0 until N) for (x in 0 until N)
            if (kotlin.math.hypot(x - C, y - C) <= r) set(x, y, v)
    }

    private fun questionMark(set: (Int, Int, Int) -> Unit) {
        // a 5x7 "?" centred, drawn in the lower right so the ring stays readable
        val glyph = listOf(
            " ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  ",
        )
        val ox = 15; val oy = 14
        glyph.forEachIndexed { y, row -> row.forEachIndexed { x, ch -> if (ch == '#') set(ox + x, oy + y, 255) } }
    }
}
