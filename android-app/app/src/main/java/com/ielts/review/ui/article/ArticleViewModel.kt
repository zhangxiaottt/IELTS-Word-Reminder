package com.ielts.review.ui.article

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.data.AppContainer
import com.ielts.review.data.ArticleRepository
import com.ielts.review.data.WordRepository
import com.ielts.review.data.local.ArticleEntity
import com.ielts.review.util.TimeUtil
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ArticleViewModel(
    private val articleRepository: ArticleRepository,
    wordRepository: WordRepository
) : ViewModel() {

    val date: String = TimeUtil.today()

    val article: StateFlow<ArticleEntity?> = articleRepository.observe(date).stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = null
    )

    /** 正文里需要高亮的复习词（熟悉度 ≤ 60 的前 20 个）。 */
    val highlightWords: StateFlow<List<String>> = wordRepository.observeAll()
        .map { rows ->
            rows.filter { it.familiar <= 60 }.take(20).map { it.word }
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList()
        )

    private val _generating = MutableStateFlow(false)
    val generating: StateFlow<Boolean> = _generating.asStateFlow()

    private val _events = Channel<String>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            articleRepository.fetch(date)
        }
    }

    fun generate() {
        if (_generating.value) return
        viewModelScope.launch {
            _generating.value = true
            val result = articleRepository.generate(date)
            _generating.value = false
            result.exceptionOrNull()?.let { _events.send(it.message ?: "生成失败") }
        }
    }

    companion object {
        fun factory(container: AppContainer) = viewModelFactory {
            initializer {
                ArticleViewModel(container.articleRepository, container.wordRepository)
            }
        }
    }
}
