package space.zhdanov.game.sudoku.requests

import android.graphics.Bitmap
import com.onyx.android.sdk.rx.RxRequest
import space.zhdanov.game.sudoku.components.RecognizeHandler

class RecognizeRequest(
    private val bitmap: Bitmap,
    private val recognizeHandler: RecognizeHandler
) : RxRequest() {

    var recognizedDigit: Int? = null
        private set

    override fun execute() {
        recognizedDigit = recognizeHandler.recognize(bitmap)
    }
}
