package com.ielts.review.ui.article

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ielts.review.data.local.ArticleEntity
import com.ielts.review.ui.theme.Primary
import com.ielts.review.ui.theme.TextSecondary
import kotlinx.coroutines.flow.collectLatest
import java.util.regex.Pattern

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ArticleScreen(
    viewModel: ArticleViewModel,
    onBack: () -> Unit
) {
    val article by viewModel.article.collectAsStateWithLifecycle()
    val generating by viewModel.generating.collectAsStateWithLifecycle()
    val highlightWords by viewModel.highlightWords.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        viewModel.events.collectLatest { message ->
            Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
        }
    }

    Scaffold(
        containerColor = Color.White,
        topBar = {
            TopAppBar(
                title = { Text("每日文章") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "返回"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            when {
                generating -> {
                    Column(
                        modifier = Modifier.fillMaxSize(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(color = Primary)
                        Spacer(Modifier.height(16.dp))
                        Text("正在生成文章，可能需要 10-30 秒…", fontSize = 13.sp, color = TextSecondary)
                    }
                }

                article == null -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "今天还没有文章",
                            fontSize = 15.sp,
                            color = TextSecondary
                        )
                        Spacer(Modifier.height(16.dp))
                        Button(
                            onClick = viewModel::generate,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text("生成今日文章")
                        }
                    }
                }

                else -> {
                    ArticleContent(
                        article = article!!,
                        highlightWords = highlightWords
                    )
                }
            }
        }
    }
}

@Composable
private fun ArticleContent(
    article: ArticleEntity,
    highlightWords: List<String>
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 16.dp)
    ) {
        Text(
            text = article.date,
            fontSize = 12.sp,
            color = TextSecondary
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = article.title,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            lineHeight = 32.sp
        )
        Spacer(Modifier.height(16.dp))
        Text(
            text = highlight(article.content, highlightWords),
            fontSize = 16.sp,
            lineHeight = 27.sp
        )
        Spacer(Modifier.height(32.dp))
    }
}

/** 把当天复习过的词在正文中高亮。 */
private fun highlight(text: String, words: List<String>): AnnotatedString {
    val valid = words.filter { it.isNotBlank() }.distinct()
    if (valid.isEmpty()) return AnnotatedString(text)

    val pattern = Pattern.compile(
        "\\b(" + valid.joinToString("|") { Pattern.quote(it) } + ")\\b",
        Pattern.CASE_INSENSITIVE
    )
    val matcher = pattern.matcher(text)

    return buildAnnotatedString {
        var last = 0
        while (matcher.find()) {
            append(text.substring(last, matcher.start()))
            withStyle(
                SpanStyle(color = Primary, fontWeight = FontWeight.Bold)
            ) {
                append(matcher.group())
            }
            last = matcher.end()
        }
        append(text.substring(last))
    }
}
