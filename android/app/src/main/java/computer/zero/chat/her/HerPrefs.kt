package computer.zero.chat.her

import android.content.Context

/** The one place the bridge address, device token and id live — read by the
 *  app, the Glyph toy service and the voice activity alike. */
class HerPrefs(context: Context) {
    private val p = context.applicationContext.getSharedPreferences("her", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = p.getString("base_url", "") ?: ""
        set(v) = p.edit().putString("base_url", v).apply()

    var token: String?
        get() = p.getString("token", null)
        set(v) = p.edit().putString("token", v).apply()

    var deviceId: String?
        get() = p.getString("device_id", null)
        set(v) = p.edit().putString("device_id", v).apply()

    val paired: Boolean get() = token != null && baseUrl.isNotEmpty()
}
