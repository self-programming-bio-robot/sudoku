package space.zhdanov.game.sudoku.components

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.res.AssetManager
import android.graphics.Bitmap
import org.json.JSONObject
import java.nio.FloatBuffer

class RecognizeHandler(private val assets: AssetManager) : AutoCloseable {
    private var session: OrtSession? = null
    private var closed = false
    private val thresholds by lazy {
        val config = assets.open("digit-recognizer.json").bufferedReader().use { JSONObject(it.readText()) }
        val labels = config.getJSONObject("output").getJSONArray("labels")
        val expectedLabels = (1..9).map(Int::toString) + "ERASE"
        require(labels.length() == expectedLabels.size)
        val configured = config.getJSONObject("thresholds")
        expectedLabels.mapIndexed { index, label ->
            require(labels.getString(index) == label)
            require(configured.has(label))
            if (configured.isNull(label)) Float.POSITIVE_INFINITY
            else configured.getDouble(label).also { require(it in 0.0..1.0) }.toFloat()
        }.toFloatArray()
    }

    @Synchronized
    fun recognize(bitmap: Bitmap): Int? {
        if (closed) return null
        val configuredThresholds = thresholds
        val environment = OrtEnvironment.getEnvironment()
        val activeSession = session ?: createSession(environment).also { session = it }

        val pixels = IntArray(IMAGE_SIZE * IMAGE_SIZE)
        bitmap.getPixels(pixels, 0, IMAGE_SIZE, 0, 0, IMAGE_SIZE, IMAGE_SIZE)
        val input = FloatArray(pixels.size) { index ->
            val pixel = pixels[index]
            val red = pixel shr 16 and 0xFF
            val green = pixel shr 8 and 0xFF
            val blue = pixel and 0xFF
            1f - (red + green + blue) / 3f / 255f
        }
        val tensor = OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), INPUT_SHAPE)
        try {
            val result = activeSession.run(mapOf("image" to tensor), setOf("scores"))
            try {
                val scores = (result[0].value as Array<*>).single() as FloatArray
                return decodeRecognition(scores, configuredThresholds)
            } finally {
                result.close()
            }
        } finally {
            tensor.close()
        }
    }

    private fun createSession(environment: OrtEnvironment): OrtSession {
        val options = OrtSession.SessionOptions()
        try {
            options.setIntraOpNumThreads(1)
            val model = assets.open("digit-recognizer.onnx").use { it.readBytes() }
            return environment.createSession(model, options)
        } finally {
            options.close()
        }
    }

    @Synchronized
    override fun close() {
        closed = true
        session?.close()
        session = null
    }

    companion object {
        const val IMAGE_SIZE = 28
        private val INPUT_SHAPE = longArrayOf(1, 1, IMAGE_SIZE.toLong(), IMAGE_SIZE.toLong())
    }
}
