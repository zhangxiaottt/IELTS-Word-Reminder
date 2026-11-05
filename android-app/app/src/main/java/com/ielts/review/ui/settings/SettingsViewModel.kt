package com.ielts.review.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ielts.review.BuildConfig
import com.ielts.review.data.AppContainer
import com.ielts.review.data.SettingsRepository
import com.ielts.review.data.WordRepository
import com.ielts.review.data.remote.ApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SettingsUiState(
    val baseUrl: String = ApiClient.DEFAULT_BASE_URL,
    val testing: Boolean = false,
    val status: String = "",
    val pending: Int = 0,
    val lastSyncAt: Long = 0L,
    val version: String = BuildConfig.VERSION_NAME
)

class SettingsViewModel(
    private val settingsRepository: SettingsRepository,
    private val wordRepository: WordRepository,
    private val apiClient: ApiClient
) : ViewModel() {

    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val url = settingsRepository.baseUrl.first()
            _state.update { it.copy(baseUrl = url) }
        }
        viewModelScope.launch {
            wordRepository.pendingCount().collect { count ->
                _state.update { it.copy(pending = count) }
            }
        }
        viewModelScope.launch {
            settingsRepository.lastSyncAt.collect { millis ->
                _state.update { it.copy(lastSyncAt = millis) }
            }
        }
    }

    fun onBaseUrlChange(value: String) {
        _state.update { it.copy(baseUrl = value, status = "") }
    }

    fun testConnection() {
        val url = _state.value.baseUrl.trim()
        if (url.isEmpty()) {
            _state.update { it.copy(status = "请先填写服务器地址") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(testing = true, status = "") }
            try {
                val resp = apiClient.service(url).health()
                val message = if (resp.code == 0) {
                    "连接成功，端口 ${resp.data?.port ?: "-"}"
                } else {
                    "连接失败：${resp.msg ?: "未知错误"}"
                }
                _state.update { it.copy(testing = false, status = message) }
            } catch (e: Exception) {
                _state.update {
                    it.copy(testing = false, status = "无法连接到服务器：${e.message ?: ""}")
                }
            }
        }
    }

    fun save() {
        val url = _state.value.baseUrl.trim()
        if (url.isEmpty()) {
            _state.update { it.copy(status = "请先填写服务器地址") }
            return
        }
        viewModelScope.launch {
            settingsRepository.setBaseUrl(url)
            _state.update { it.copy(baseUrl = url.trim().trimEnd('/'), status = "已保存") }
            wordRepository.refresh()
        }
    }

    companion object {
        fun factory(container: AppContainer) = viewModelFactory {
            initializer {
                SettingsViewModel(
                    container.settingsRepository,
                    container.wordRepository,
                    container.apiClient
                )
            }
        }
    }
}
