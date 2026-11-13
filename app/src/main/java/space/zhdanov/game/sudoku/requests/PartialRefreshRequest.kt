package space.zhdanov.game.sudoku.requests

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.RectF
import com.onyx.android.sdk.api.device.epd.EpdController
import com.onyx.android.sdk.api.device.epd.UpdateMode
import com.onyx.android.sdk.pen.TouchHelper
import com.onyx.android.sdk.rx.RxRequest
import com.onyx.android.sdk.utils.RectUtils
import space.zhdanov.game.sudoku.components.GameView
import space.zhdanov.game.sudoku.utils.drawRendererContent
import space.zhdanov.game.sudoku.utils.plus

class PartialRefreshRequest(
    context: Context,
    private val surfaceView: GameView,
    private val refreshRect: List<RectF>,
    private val fieldBitmap: Bitmap,
    private val touchHelper: TouchHelper,
    private val penEnable: Boolean,
    private val isActive: () -> Boolean
) : RxRequest() {

    @Throws(Exception::class)
    override fun execute() {
        renderToScreen(surfaceView)
    }

    private fun renderToScreen(surfaceView: GameView) {
        if (!isActive()) return
        val bounds = refreshRect.reduce { acc, rectF -> acc + rectF }
        if (bounds.isEmpty) return
        val renderRect = RectUtils.toRect(bounds)
        val canvas = surfaceView.holder.lockCanvas(renderRect) ?: return
        try {
            if (!isActive()) return
            touchHelper.setRawDrawingRenderEnabled(false)
            EpdController.setViewDefaultUpdateMode(surfaceView, UpdateMode.HAND_WRITING_REPAINT_MODE)
            canvas.clipRect(bounds)
            surfaceView.onRender?.let { it(canvas) }
                ?: run {
                    canvas.drawColor(Color.WHITE)
                    drawRendererContent(fieldBitmap, canvas)
                }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            surfaceView.holder.unlockCanvasAndPost(canvas)
            EpdController.resetViewUpdateMode(surfaceView)
            if (isActive()) touchHelper.setRawDrawingRenderEnabled(penEnable)
        }

    }

    init {
        setContext(context)
    }
}
