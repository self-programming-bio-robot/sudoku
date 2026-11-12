package space.zhdanov.game.sudoku

import android.annotation.SuppressLint
import android.graphics.drawable.BitmapDrawable
import android.os.Bundle
import android.support.v7.app.AppCompatActivity
import android.view.View
import android.widget.TextView
import space.zhdanov.game.sudoku.databinding.ActivityFinishGameBinding
import space.zhdanov.game.sudoku.utils.TITLE_EXTRA

class FinishGameActivity : AppCompatActivity() {

    private lateinit var binding: ActivityFinishGameBinding
    private lateinit var titleText: TextView

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        binding = ActivityFinishGameBinding.inflate(layoutInflater)
        titleText = binding.finishTitle
        val finishButton = binding.finish
        val retryButton = binding.retry

        setContentView(binding.root)

        binding.root.systemUiVisibility = View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION

        titleText.text = intent.getStringExtra(TITLE_EXTRA)

        GameActivity.background?.let { background ->
            binding.root.background = BitmapDrawable(resources, background)
        }

        finishButton.setOnClickListener {
            setResult(RESULT_OK)
            finish()
        }

        retryButton.setOnClickListener {
            setResult(RESULT_RETRY)
            finish()
        }
    }

    companion object {
        const val RESULT_RETRY = RESULT_FIRST_USER
    }
}
