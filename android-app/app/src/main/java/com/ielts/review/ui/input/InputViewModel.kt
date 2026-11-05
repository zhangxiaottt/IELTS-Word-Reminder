package com.ielts.review.ui.input

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.data.AppContainer
import com.ielts.review.data.NetworkMonitor
import com.ielts.review.data.SaveResult
import com.ielts.review.data.WordRepository
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class InputUiState(
    val word: String = "",
    val phonetic: String = "",
    val meaning: String = "",
    val example: String = "",
    val dictLoading: Boolean = false,
    val saving: Boolean = false,
    val duplicateId: Long? = null,
    /** 自增后触发输入框重新聚焦 */
    val focusTick: Int = 0
)

class InputViewModel(
    private val wordRepository: WordRepository,
    private val monitor: NetworkMonitor
) : ViewModel() {

    private val _state = MutableStateFlow(InputUiState())
    val state: StateFlow<InputUiState> = _state.asStateFlow()

    private val _events = Channel<String>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    fun onWordChange(value: String) {
        _state.update { it.copy(word = value) }
    }

    fun onPhoneticChange(value: String) {
        _state.update { it.copy(phonetic = value) }
    }

    fun onMeaningChange(value: String) {
        _state.update { it.copy(meaning = value) }
    }

    fun onExampleChange(value: String) {
        _state.update { it.copy(example = value) }
    }

    /** 查询释义：音标只读，释义/例句可再编辑。 */
    fun lookup() {
        val word = _state.value.word.trim()
        if (word.isEmpty()) {
            _events.trySend("请输入英文单词")
            return
        }
        if (!monitor.isCurrentlyOnline()) {
            _events.trySend("当前离线，无法查询释义")
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(dictLoading = true) }
            val dto = wordRepository.lookupDict(word)
            if (dto == null) {
                _state.update { it.copy(dictLoading = false) }
                _events.send("查询失败，请检查服务器地址")
                return@launch
            }
            val empty = dto.phonetic.isBlank() && dto.meaning.isBlank() && dto.example.isBlank()
            _state.update {
                it.copy(
                    phonetic = dto.phonetic,
                    meaning = if (dto.meaning.isNotBlank()) dto.meaning else it.meaning,
                    example = if (dto.example.isNotBlank()) dto.example else it.example,
                    dictLoading = false
                )
            }
            if (empty) {
                _events.send("未查到该单词，请手动填写释义")
            }
        }
    }

    /** 保存：在线先 POST；离线写本地 dirty 队列。 */
    fun save() {
        val s = _state.value
        if (s.saving) return
        if (s.word.isBlank()) {
            _events.trySend("请输入英文单词")
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(saving = true) }
            when (val result = wordRepository.saveNewWord(s.word, s.phonetic, s.meaning, s.example)) {
                is SaveResult.Success -> {
                    _events.send(if (result.offline) "已离线保存，联网后自动同步" else "已保存")
                    clearFields()
                }

                is SaveResult.Duplicate -> {
                    var id = wordRepository.findExactRemote(s.word.trim())
                    if (id == null) {
                        id = wordRepository.findLocalExact(s.word.trim())
                    }
                    if (id == null) {
                        _state.update { it.copy(saving = false, duplicateId = -1L) }
                        _events.send("该单词已收录，但未找到对应记录，可到单词本中修改")
                    } else {
                        _state.update { it.copy(saving = false, duplicateId = id) }
                    }
                }

                is SaveResult.Error -> {
                    _state.update { it.copy(saving = false) }
                    _events.send(result.message)
                }
            }
        }
    }

    fun dismissDuplicate() {
        _state.update { it.copy(duplicateId = null) }
    }

    /** 确认覆盖：PUT 已有记录。 */
    fun confirmOverwrite() {
        val s = _state.value
        val id = s.duplicateId ?: return
        if (id < 0) {
            dismissDuplicate()
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(saving = true) }
            val ok = wordRepository.overwrite(id, s.meaning, s.example)
            _state.update { it.copy(duplicateId = null, saving = false) }
            _events.send(if (ok) "已更新" else "本地已更新，联网后自动同步")
            clearFields()
        }
    }

    private fun clearFields() {
        _state.update {
            it.copy(
                word = "",
                phonetic = "",
                meaning = "",
                example = "",
                saving = false,
                focusTick = it.focusTick + 1
            )
        }
    }

    companion object {
        fun factory(container: AppContainer) = viewModelFactory {
            initializer { InputViewModel(container.wordRepository, container.networkMonitor) }
        }
    }
}
