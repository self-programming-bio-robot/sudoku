package space.zhdanov.game.sudoku.components

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.graphics.RectF
import android.util.Log
import com.onyx.android.sdk.pen.RawInputCallback
import com.onyx.android.sdk.pen.TouchHelper
import com.onyx.android.sdk.pen.data.TouchPoint
import com.onyx.android.sdk.pen.data.TouchPointList
import com.onyx.android.sdk.rx.RxCallback
import com.onyx.android.sdk.rx.RxManager
import space.zhdanov.game.sudoku.models.Field
import space.zhdanov.game.sudoku.models.Grid.Companion.FIELD_SIZE
import space.zhdanov.game.sudoku.requests.PartialRefreshRequest
import space.zhdanov.game.sudoku.requests.RecognizeRequest
import space.zhdanov.game.sudoku.utils.extend
import space.zhdanov.game.sudoku.utils.intersection
import space.zhdanov.game.sudoku.utils.normalize
import space.zhdanov.game.sudoku.utils.plus
import kotlin.math.max
import kotlin.math.min

class PenHandler(
    width: Int,
    height: Int,
    private val context: Context,
    private val surfaceView: GameView,
    private val field: Field,
    private val recognizeHandler: RecognizeHandler,
) : RawInputCallback() {
    var penEnable: Boolean = true
    private val bitmap: Bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    private val canvas: Canvas = Canvas(bitmap)
    private val rxManager = RxManager.Builder.sharedSingleThreadManager()
    private val drawRect: RectF = RectF(startRect)
    private val strokeLock = Any()
    @Volatile
    private var active = true

    lateinit var touchHelper: TouchHelper

    var onRecognizeDigit: ((x: Int, y: Int, digit: Int) -> Boolean)? = null

    init {
        canvas.drawColor(Color.WHITE)
    }

    override fun onBeginRawDrawing(p0: Boolean, p1: TouchPoint) {
    }

    override fun onEndRawDrawing(p0: Boolean, p1: TouchPoint) {
    }

    override fun onRawDrawingTouchPointMoveReceived(p0: TouchPoint) {
    }

    override fun onRawDrawingTouchPointListReceived(points: TouchPointList) {
        synchronized(strokeLock) {
            if (active && points.points.isNotEmpty()) drawScribbleToBitmap(points.points)
        }
    }

    override fun onBeginRawErasing(p0: Boolean, p1: TouchPoint) {
    }

    override fun onEndRawErasing(p0: Boolean, p1: TouchPoint) {
    }

    override fun onRawErasingTouchPointMoveReceived(p0: TouchPoint) {
    }

    override fun onRawErasingTouchPointListReceived(p0: TouchPointList) {
    }

    fun deactivate() {
        active = false
    }

    override fun onPenUpRefresh(refreshRect: RectF) {
        val inkRect = RectF(refreshRect)
        val (stroke, bounds) = synchronized(strokeLock) {
            if (!active || drawRect == startRect) return
            val bounds = RectF(drawRect)
            val normalized = field.getCellRect(bounds).intersection(bounds).normalize()
            val stroke = if (normalized.width() >= 0f && normalized.height() >= 0f) {
                val crop = normalized.extend(max(normalized.width() / 5, paint.strokeWidth / 2))
                val size = RecognizeHandler.IMAGE_SIZE
                Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).also { snapshot ->
                    Canvas(snapshot).apply {
                        drawColor(Color.WHITE)
                        scale(size / crop.width(), size / crop.height())
                        translate(-crop.left, -crop.top)
                        drawBitmap(bitmap, 0f, 0f, Paint(Paint.FILTER_BITMAP_FLAG))
                    }
                }
            } else null
            canvas.drawColor(Color.WHITE)
            drawRect.set(startRect)
            Pair(stroke, bounds)
        }

        val (x, y) = field.getCellCoordinates(bounds.centerX(), bounds.centerY())
        if (stroke == null || x !in 0 until FIELD_SIZE || y !in 0 until FIELD_SIZE || field.grid.isStartedCell(x, y)) {
            refreshInk(listOf(inkRect))
            return
        }

        val cellRect = field.getCellRect(x, y)
        val recognizeRequest = RecognizeRequest(stroke, recognizeHandler)
        rxManager.enqueue(
            recognizeRequest,
            object : RxCallback<RecognizeRequest>() {
                override fun onNext(request: RecognizeRequest) {
                    if (!active) return
                    val digit = request.recognizedDigit
                    if (digit == null) {
                        refreshInk(listOf(inkRect))
                        return
                    }
                    val lastMistakeRects = field.getRectOfMistakes()
                    val updated = onRecognizeDigit?.let {
                        it(x, y, digit)
                    } ?: run {
                        field.grid.changeCell(x, y, digit)
                    }

                    if (updated) field.draw()
                    val dirtyRects = if (updated) {
                        listOf(cellRect + inkRect) + field.getRectOfMistakes() + lastMistakeRects
                    } else listOf(inkRect)
                    refreshInk(dirtyRects)
                }

                override fun onError(error: Throwable) {
                    Log.e("recognize", "Failed to recognize ink", error)
                    refreshInk(listOf(inkRect))
                }
            }
        )
    }

    private fun refreshInk(rects: List<RectF>) {
        if (!active) return
        val request = PartialRefreshRequest(
            context, surfaceView, rects, field.bitmap, touchHelper, penEnable, isActive = { active }
        )
        rxManager.enqueue(request, object : RxCallback<PartialRefreshRequest>() {
            override fun onNext(request: PartialRefreshRequest) = Unit
        })
    }

    private fun drawScribbleToBitmap(list: List<TouchPoint>) {
        val path = Path()
        val prePoint = PointF(list[0].x, list[0].y)
        path.moveTo(prePoint.x, prePoint.y)
        for (point in list) {
            path.quadTo(prePoint.x, prePoint.y, point.x, point.y)
            prePoint.x = point.x
            prePoint.y = point.y

            drawRect.left = min(drawRect.left, point.x)
            drawRect.right = max(drawRect.right, point.x)
            drawRect.top = min(drawRect.top, point.y)
            drawRect.bottom = max(drawRect.bottom, point.y)
        }

        canvas.drawPath(path, paint)
    }

    companion object {
        val paint = Paint().apply {
            isAntiAlias = true
            strokeWidth = 13f
            style = Paint.Style.STROKE
            color = Color.BLACK
        }

        private val startRect = RectF(10000f, 10000f, 0f, 0f)
    }
}
