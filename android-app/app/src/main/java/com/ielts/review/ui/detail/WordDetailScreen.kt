package com.ielts.review.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ielts.review.data.local.WordEntity
import com.ielts.review.ui.common.orDash
import com.ielts.review.ui.theme.Danger
import com.ielts.review.ui.theme.DividerColor
import com.ielts.review.ui.theme.Primary
import com.ielts.review.ui.theme.PrimaryContainer
import com.ielts.review.ui.theme.SurfaceVariant
import com.ielts.review.ui.theme.TextSecondary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WordDetailScreen(
    viewModel: WordDetailViewModel,
    onBack: () -> Unit
) {
    val word by viewModel.word.collectAsStateWithLifecycle()
    var showEdit by remember { mutableStateOf(false) }
    var showDelete by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = Color.White,
        topBar = {
            TopAppBar(
                title = { Text("单词详情") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "返回"
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { showEdit = true }) {
                        Icon(Icons.Filled.Edit, contentDescription = "编辑", tint = TextSecondary)
                    }
                    IconButton(onClick = { showDelete = true }) {
                        Icon(Icons.Filled.Delete, contentDescription = "删除", tint = Danger)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { padding ->
        val current = word
        if (current == null) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(color = Primary)
            }
        } else {
            DetailContent(word = current, modifier = Modifier.padding(padding))
        }
    }

    if (showEdit && word != null) {
        EditWordDialog(
            initialMeaning = word?.meaning.orEmpty(),
            initialExample = word?.example.orEmpty(),
            onDismiss = { showEdit = false },
            onSave = { meaning, example ->
                viewModel.saveContent(meaning, example)
                showEdit = false
            }
        )
    }

    if (showDelete) {
        AlertDialog(
            onDismissRequest = { showDelete = false },
            title = { Text("删除单词") },
            text = { Text("确定要删除「${word?.word ?: ""}」吗？此操作会同步到电脑端。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDelete = false
                        viewModel.delete()
                        onBack()
                    }
                ) {
                    Text("删除", color = Danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDelete = false }) { Text("取消") }
            }
        )
    }
}

@Composable
private fun DetailContent(word: WordEntity, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 16.dp)
    ) {
        Text(
            text = word.word,
            fontSize = 36.sp,
            fontWeight = FontWeight.Bold
        )
        if (word.phonetic.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(text = word.phonetic, fontSize = 16.sp, color = TextSecondary)
        }

        Spacer(Modifier.height(20.dp))

        Card(
            shape = RoundedCornerShape(14.dp),
            colors = CardDefaults.cardColors(containerColor = SurfaceVariant)
        ) {
            Column(Modifier.padding(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "熟悉度",
                        fontSize = 13.sp,
                        color = TextSecondary,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = "${word.familiar} / 100",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Primary
                    )
                }
                LinearProgressIndicator(
                    progress = { word.familiar / 100f },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp)
                        .height(5.dp),
                    color = Primary,
                    trackColor = PrimaryContainer
                )
                Spacer(Modifier.height(12.dp))
                HorizontalDivider(color = DividerColor)
                Spacer(Modifier.height(12.dp))
                InfoRow("复习次数", "${word.reviewCount}")
                InfoRow("创建时间", word.createdAt.orDash())
                InfoRow("最近复习", word.lastReview.orDash())
            }
        }

        Spacer(Modifier.height(16.dp))
        SectionCard(title = "释义", body = word.meaning.orDash())
        Spacer(Modifier.height(12.dp))
        SectionCard(
            title = "例句",
            body = word.example.orDash(),
            italic = true
        )
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp)
    ) {
        Text(text = label, fontSize = 13.sp, color = TextSecondary, modifier = Modifier.weight(1f))
        Text(text = value, fontSize = 13.sp)
    }
}

@Composable
private fun SectionCard(title: String, body: String, italic: Boolean = false) {
    Card(
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(text = title, fontSize = 13.sp, color = TextSecondary)
            Spacer(Modifier.height(6.dp))
            Text(
                text = body,
                fontSize = 16.sp,
                lineHeight = 24.sp,
                fontStyle = if (italic) FontStyle.Italic else FontStyle.Normal
            )
        }
    }
}

@Composable
private fun EditWordDialog(
    initialMeaning: String,
    initialExample: String,
    onDismiss: () -> Unit,
    onSave: (String, String) -> Unit
) {
    var meaning by remember(initialMeaning) { mutableStateOf(initialMeaning) }
    var example by remember(initialExample) { mutableStateOf(initialExample) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("编辑释义") },
        text = {
            Column {
                OutlinedTextField(
                    value = meaning,
                    onValueChange = { meaning = it },
                    label = { Text("释义") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = example,
                    onValueChange = { example = it },
                    label = { Text("例句") },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(meaning.trim(), example.trim()) }) {
                Text("保存")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("取消") }
        }
    )
}
