package com.ielts.review.ui.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.data.AppContainer
import com.ielts.review.data.NetworkMonitor
import com.ielts.review.data.WordRepository
import com.ielts.review.data.local.WordEntity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ReviewUiState(
    val cards: List<WordEntity> = emptyList(),
    val index: Int = 0,
    val revealed: Boolean = false,
    val loading: Boolean = true,
    val finished: Boolean = false,
    val empty: Boolean = false,
    val isOnline: Boolean = true
)

class ReviewViewModel(
    private val wordRepository: WordRepository,
    private val monitor: NetworkMonitor
) : ViewModel() {

    private val _state = MutableStateFlow(ReviewUiState())
    val state: StateFlow<ReviewUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            monitor.isOnline.collect { online ->
                _state.update { it.copy(isOnline = online) }
            }
        }
        loadRound()
    }

    fun loadRound() {
        viewModelScope.launch {
            _state.update {
                it.copy(loading = true, finished = false, empty = false, index = 0, revealed = false)
            }
            // 先把后端随机词并入本地缓存；失败不影响离线复习
            runCatching { wordRepository.refreshRandom(20, 60) }
            val cards = wordRepository.randomCandidates(60, 20)
            _state.update {
                it.copy(
                    cards = cards,
                    index = 0,
                    revealed = false,
                    loading = false,
                    empty = cards.isEmpty(),
                    finished = false
                )
            }
        }
    }

    fun reveal() {
        _state.update { it.copy(revealed = !it.revealed) }
    }

    fun answer(known: Boolean) {
        val current = _state.value
        val card = current.cards.getOrNull(current.index) ?: return
        val nextIndex = current.index + 1
        _state.update {
            it.copy(
                index = nextIndex,
                revealed = false,
                finished = nextIndex >= it.cards.size
            )
        }
        viewModelScope.launch { wordRepository.markFamiliar(card, known) }
    }

    companion object {
        fun factory(container: AppContainer) = viewModelFactory {
            initializer { ReviewViewModel(container.wordRepository, container.networkMonitor) }
        }
    }
}
