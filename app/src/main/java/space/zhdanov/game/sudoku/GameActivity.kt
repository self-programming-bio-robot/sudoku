package space.zhdanov.game.sudoku

import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.Bundle
import android.support.v7.app.AppCompatActivity
import android.util.Log
import android.view.Window
import android.view.WindowManager
import com.onyx.android.sdk.rx.RxManager
import io.sentry.Sentry
import space.zhdanov.game.sudoku.components.GameView
import space.zhdanov.game.sudoku.databinding.ActivityGameBinding
import space.zhdanov.game.sudoku.models.Grid
import space.zhdanov.game.sudoku.models.Grid.Companion.FIELD_SIZE
import space.zhdanov.game.sudoku.utils.CONTINUE_EXTRA
import space.zhdanov.game.sudoku.utils.CONTINUE_PREFERENCES
import space.zhdanov.game.sudoku.utils.DEFAULT_DIFFICULTY
import space.zhdanov.game.sudoku.utils.DIFFICULT_EXTRA
import space.zhdanov.game.sudoku.utils.GAME_PREFERENCES_FILE
import space.zhdanov.game.sudoku.utils.PLAYER_SOLUTION_PREFERENCES
import space.zhdanov.game.sudoku.utils.STARTED_GRID_PREFERENCES
import space.zhdanov.game.sudoku.utils.TITLE_EXTRA
import space.zhdanov.game.sudoku.utils.array2dFromStrings

class GameActivity : AppCompatActivity() {

    private val LOG_TAG = GameActivity::class.qualifiedName

    private lateinit var surfaceView: GameView
    private lateinit var grid: Grid
    private lateinit var preferences: SharedPreferences
    private var difficulty = DEFAULT_DIFFICULTY

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        RxManager.Builder.initAppContext(application)
        preferences = getSharedPreferences(GAME_PREFERENCES_FILE, MODE_PRIVATE)

        requestWindowFeature(Window.FEATURE_NO_TITLE)
        window.setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN)

        difficulty = intent.getIntExtra(DIFFICULT_EXTRA, DEFAULT_DIFFICULTY)
        if (savedInstanceState != null || intent.getBooleanExtra(CONTINUE_EXTRA, false)) {
            val restoredGrid = restoreGrid(savedInstanceState)
            if (restoredGrid == null) {
                finish()
                return
            }
            grid = restoredGrid
        } else {
            grid = Grid(difficulty) { onGameCompleted() }
            saveGame()
        }
        grid.onChanged = { completed ->
            if (!isFinishing) {
                if (completed) clearSavedGame() else saveGame()
            }
        }
        val binding = ActivityGameBinding.inflate(layoutInflater)
        surfaceView = binding.surfaceView
        surfaceView.grid = grid

        setContentView(binding.root)
    }

    override fun onBackPressed() {
        gotoFinishActivity("Pause")
    }

    override fun onSaveInstanceState(outState: Bundle?) {
        super.onSaveInstanceState(outState)
        if (::grid.isInitialized && outState != null) {
            outState.putInt(DIFFICULT_EXTRA, difficulty)
            outState.putString(STARTED_GRID_PREFERENCES, grid.firstRepresentation.joinToString(","))
            outState.putString(PLAYER_SOLUTION_PREFERENCES, grid.grid.joinToString(","))
        }
    }

    private fun restoreGrid(state: Bundle?): Grid? {
        return try {
            val startedGrid: String?
            val playerSolution: String?
            // Preferences may contain a move processed after the Activity state was saved.
            if (preferences.getBoolean(CONTINUE_PREFERENCES, false)) {
                difficulty = preferences.getInt(DIFFICULT_EXTRA, difficulty)
                startedGrid = preferences.getString(STARTED_GRID_PREFERENCES, null)
                playerSolution = preferences.getString(PLAYER_SOLUTION_PREFERENCES, null)
            } else if (state?.containsKey(STARTED_GRID_PREFERENCES) == true) {
                difficulty = state.getInt(DIFFICULT_EXTRA, difficulty)
                startedGrid = state.getString(STARTED_GRID_PREFERENCES)
                playerSolution = state.getString(PLAYER_SOLUTION_PREFERENCES)
            } else {
                return null
            }

            val initial = array2dFromStrings(FIELD_SIZE, FIELD_SIZE, requireNotNull(startedGrid))
            val played = array2dFromStrings(FIELD_SIZE, FIELD_SIZE, requireNotNull(playerSolution))
            require(initial.zip(played).all { (clue, value) -> clue == 0 || clue == value })
            Grid(initial) { onGameCompleted() }.apply { loadUserSolution(played) }
        } catch (e: IllegalArgumentException) {
            discardInvalidGame(e)
            null
        } catch (e: ClassCastException) {
            discardInvalidGame(e)
            null
        }
    }

    private fun saveGame() {
        preferences.edit()
            .putBoolean(CONTINUE_PREFERENCES, true)
            .putInt(DIFFICULT_EXTRA, difficulty)
            .putString(STARTED_GRID_PREFERENCES, grid.firstRepresentation.joinToString(","))
            .putString(PLAYER_SOLUTION_PREFERENCES, grid.grid.joinToString(","))
            .apply()
    }

    private fun discardInvalidGame(e: RuntimeException) {
        Log.e(LOG_TAG, "Fail of loading state", e)
        Sentry.captureException(e)
        clearSavedGame()
    }

    private fun clearSavedGame() {
        preferences.edit()
            .remove(CONTINUE_PREFERENCES)
            .remove(DIFFICULT_EXTRA)
            .remove(STARTED_GRID_PREFERENCES)
            .remove(PLAYER_SOLUTION_PREFERENCES)
            .apply()
    }

    private fun onGameCompleted() {
        if (!isFinishing) gotoFinishActivity(getString(R.string.score))
    }

    private fun gotoFinishActivity(title: String) {
        val intent = Intent(this, FinishGameActivity::class.java)
        intent.putExtra(TITLE_EXTRA, title)
        surfaceView.render()
        background = surfaceView.getBitmap()
        startActivityForResult(intent, FINISH_GAME_REQUEST)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != FINISH_GAME_REQUEST || !::grid.isInitialized) return

        if (resultCode == FinishGameActivity.RESULT_RETRY) {
            startActivity(Intent(this, GameActivity::class.java).putExtra(DIFFICULT_EXTRA, difficulty))
            finish()
        } else if (resultCode == RESULT_OK || grid.checkSuccess()) {
            finish()
        }
    }

    companion object {
        var background: Bitmap? = null
        private const val FINISH_GAME_REQUEST = 1
    }
}
