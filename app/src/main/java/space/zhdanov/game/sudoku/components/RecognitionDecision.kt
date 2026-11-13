package space.zhdanov.game.sudoku.components

// Grid uses 0 to clear a cell. A null result leaves the cell unchanged.
internal fun decodeRecognition(scores: FloatArray, thresholds: FloatArray): Int? {
    if (scores.size != 10 || thresholds.size != scores.size || scores.any { !it.isFinite() }) return null
    val winner = scores.indices.maxByOrNull { scores[it] } ?: return null
    if (scores[winner] <= thresholds[winner]) return null
    return if (winner == 9) 0 else winner + 1
}
