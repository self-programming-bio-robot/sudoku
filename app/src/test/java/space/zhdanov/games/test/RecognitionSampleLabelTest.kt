package space.zhdanov.games.test

import org.junit.Assert.assertEquals
import org.junit.Test
import space.zhdanov.game.sudoku.components.sampleLabel

class RecognitionSampleLabelTest {
    @Test
    fun filledCellTakesPrecedenceOverTheModelResult() {
        for (result in listOf(null, 0, 7)) {
            assertEquals("ERASE", sampleLabel(cellWasFilled = true, recognizedDigit = result))
        }
    }

    @Test
    fun emptyCellUsesTheModelResultWhenAvailable() {
        assertEquals("unlabeled", sampleLabel(cellWasFilled = false, recognizedDigit = null))
        assertEquals("7", sampleLabel(cellWasFilled = false, recognizedDigit = 7))
        assertEquals("ERASE", sampleLabel(cellWasFilled = false, recognizedDigit = 0))
    }
}
