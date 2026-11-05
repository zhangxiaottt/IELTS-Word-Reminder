package com.ielts.review.ui.input

import android.widget.Toast
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ielts.review.ui.theme.TextSecondary
import kotlinx.coroutines.flow.collectLatest

@Composable
fun InputScreen(viewModel: InputViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(state.focusTick) {
        if (state.focusTick > 0) {
            focusRequester.requestFocus()
        }
    }

    LaunchedEffect(Unit) {
        viewModel.events.collectLatest { message ->
            Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(text = "录入单词", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = state.word,
                onValueChange = viewModel::onWordChange,
                modifier = Modifier
                    .weight(1f)
                    .focusRequester(focusRequester),
                label = { Text("单词") },
                singleLine = true,
                shape = RoundedCornerShape(12.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { viewModel.lookup() })
            )
            Spacer(Modifier.width(10.dp))
            Button(
                onClick = viewModel::lookup,
                enabled = !state.dictLoading,
                modifier = Modifier
                    .width(88.dp)
                    .height(56.dp),
                shape = RoundedCornerShape(12.dp)
            ) {
                if (state.dictLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = androidx.compose.ui.graphics.Color.White,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("查询")
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = state.phonetic,
            onValueChange = viewModel::onPhoneticChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("音标") },
            singleLine = true,
            readOnly = true,
            shape = RoundedCornerShape(12.dp),
            supportingText = { Text("音标由词典自动填充") }
        )

        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = state.meaning,
            onValueChange = viewModel::onMeaningChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("释义") },
            minLines = 3,
            shape = RoundedCornerShape(12.dp)
        )

        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = state.example,
            onValueChange = viewModel::onExampleChange,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 96.dp),
            label = { Text("例句") },
            minLines = 3,
            shape = RoundedCornerShape(12.dp)
        )

        Spacer(Modifier.height(24.dp))
        Button(
            onClick = viewModel::save,
            enabled = !state.saving,
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            shape = RoundedCornerShape(12.dp)
        ) {
            if (state.saving) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    color = androidx.compose.ui.graphics.Color.White,
                    strokeWidth = 2.dp
                )
            } else {
                Text("保存", fontSize = 16.sp)
            }
        }

        Spacer(Modifier.height(12.dp))
        Text(
            text = "离线时也可以录入，联网后会自动补传到电脑端。",
            fontSize = 12.sp,
            color = TextSecondary
        )
    }

    if (state.duplicateId != null) {
        AlertDialog(
            onDismissRequest = viewModel::dismissDuplicate,
            title = { Text("该单词已收录") },
            text = { Text("是否用当前内容覆盖已有的释义和例句？") },
            confirmButton = {
                TextButton(
                    onClick = viewModel::confirmOverwrite,
                    enabled = state.duplicateId != -1L
                ) {
                    Text("覆盖更新")
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::dismissDuplicate) { Text("取消") }
            }
        )
    }
}
