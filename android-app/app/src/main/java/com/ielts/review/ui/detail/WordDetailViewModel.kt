package com.ielts.review.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.data.AppContainer
import com.ielts.review.data.WordRepository
import com.ielts.review.data.local.WordEntity
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class WordDetailViewModel(
    private val wordRepository: WordRepository,
    private val wordId: Long
) : ViewModel() {

    val word: StateFlow<WordEntity?> = wordRepository.observeById(wordId).stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = null
    )

    fun saveContent(meaning: String, example: String) {
        viewModelScope.launch {
            wordRepository.updateContent(wordId, meaning, example)
        }
    }

    fun delete() {
        viewModelScope.launch {
            wordRepository.delete(wordId)
        }
    }

    companion object {
        fun factory(container: AppContainer, wordId: Long) = viewModelFactory {
            initializer { WordDetailViewModel(container.wordRepository, wordId) }
        }
    }
}
