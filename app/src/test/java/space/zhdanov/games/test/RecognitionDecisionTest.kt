package space.zhdanov.games.test

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import space.zhdanov.game.sudoku.components.decodeRecognition

class RecognitionDecisionTest {
    private val thresholds = FloatArray(10) { 0.5f }.apply { this[9] = 0.475f }

    @Test
    fun digitAndEraseUseTheirOwnThresholds() {
        assertEquals(7, decodeRecognition(FloatArray(10).apply { this[6] = 0.9f }, thresholds))
        assertEquals(0, decodeRecognition(FloatArray(10).apply { this[9] = 0.49f }, thresholds))
    }

    @Test
    fun rejectedWinnerDoesNotFallBackToAnotherAction() {
        val scores = FloatArray(10).apply {
            this[0] = 0.5f
            this[9] = 0.49f
        }
        assertNull(decodeRecognition(scores, thresholds))
        scores[9] = Float.NaN
        assertNull(decodeRecognition(scores, thresholds))
    }
}
