package space.zhdanov.game.sudoku.components

import android.graphics.Bitmap
import android.util.Log
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.Executors

internal fun sampleLabel(cellWasFilled: Boolean, recognizedDigit: Int?): String = when {
    cellWasFilled || recognizedDigit == 0 -> "ERASE"
    recognizedDigit != null -> recognizedDigit.toString()
    else -> "unlabeled"
}

internal object RecognitionSamples {
    private val writer = Executors.newSingleThreadExecutor()

    fun save(storageRoot: File, stroke: Bitmap, label: String) {
        writer.execute {
            val directory = File(storageRoot, "recognition-samples")
            val id = UUID.randomUUID().toString()
            val sample = File(directory, "$id--$label.png")
            val pending = File(directory, "$id.tmp")
            try {
                if (!directory.isDirectory && !directory.mkdirs()) {
                    throw IOException("Could not create the recognition samples directory")
                }
                pending.outputStream().use { stream ->
                    if (!stroke.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                        throw IOException("Could not encode the recognition sample")
                    }
                }
                if (!pending.renameTo(sample)) throw IOException("Could not publish the recognition sample")
            } catch (error: IOException) {
                Log.w("recognize", "Could not save the recognition sample", error)
            } finally {
                pending.delete()
            }
        }
    }
}
