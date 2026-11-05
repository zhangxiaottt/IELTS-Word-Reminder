package com.ielts.review.ui.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.data.AppContainer
import com.ielts.review.data.NetworkMonitor
import com.ielts.review.data.WordRepository
import com.ielts.review.data.local.WordEntity
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@OptIn(FlowPreview::class, ExperimentalCoroutinesApi::class)
class LibraryViewModel(
    private val wordRepository: WordRepository,
    private val monitor: NetworkMonitor
) : ViewModel() {

    private val _keyword = MutableStateFlow("")
    val keyword: StateFlow<String> = _keyword.asStateFlow()

    private val _refreshing = MutableStateFlow(false)
    val refreshing: StateFlow<Boolean> = _refreshing.asStateFlow()

    val isOnline: StateFlow<Boolean> = monitor.isOnline.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = monitor.isCurrentlyOnline()
    )

    val words: StateFlow<List<WordEntity>> = _keyword
        .debounce(250)
        .distinctUntilChanged()
        .flatMapLatest { keyword -> wordRepository.search(keyword) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList()
        )

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val messages = _messages.asSharedFlow()

    init {
        viewModelScope.launch {
            _keyword
                .debounce(400)
                .distinctUntilChanged()
                .collect { keyword ->
                    if (keyword.isNotBlank()) {
                        runCatching { wordRepository.searchRemote(keyword.trim()) }
                    }
                }
        }
    }

    fun onKeywordChange(value: String) {
        _keyword.value = value
    }

    fun refresh() {
        viewModelScope.launch {
            _refreshing.value = true
            val result = wordRepository.refresh()
            _refreshing.value = false
            if (!result.ok) {
                _messages.emit("无法连接到服务器")
            }
        }
    }

    companion object {
        fun factory(container: AppContainer) = viewModelFactory {
            initializer { LibraryViewModel(container.wordRepository, container.networkMonitor) }
        }
    }
}
