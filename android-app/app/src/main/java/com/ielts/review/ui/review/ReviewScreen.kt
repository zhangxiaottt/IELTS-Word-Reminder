package com.ielts.review.ui.review

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ielts.review.data.local.WordEntity
import com.ielts.review.ui.common.EmptyHint
import com.ielts.review.ui.theme.DividerColor
import com.ielts.review.ui.theme.Danger
import com.ielts.review.ui.theme.Primary
import com.ielts.review.ui.theme.PrimaryContainer
import com.ielts.review.ui.theme.Success
import com.ielts.review.ui.theme.TextSecondary

@Composable
fun ReviewScreen(
    viewModel: ReviewViewModel,
    onOpenSettings: () -> Unit,
    onOpenArticle: () -> Unit
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "今日复习",
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f)
            )
            IconButton(onClick = onOpenSettings) {
                Icon(Icons.Filled.Settings, contentDescription = "设置", tint = TextSecondary)
            }
        }

        ArticleBanner(onClick = onOpenArticle)
        Spacer(Modifier.height(16.dp))

        when {
            state.loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = Primary)
                }
            }

            state.empty -> {
                EmptyHint(
                    title = "还没有可复习的单词\n请先在设置页填写电脑端服务地址，并同步词库",
                    actionText = "去设置",
                    onAction = onOpenSettings,
                    modifier = Modifier.weight(1f)
                )
            }

            state.finished -> {
                FinishedRound(
                    total = state.cards.size,
                    onRestart = viewModel::loadRound,
                    modifier = Modifier.weight(1f)
                )
            }

            else -> {
                ReviewBody(
                    state = state,
                    onReveal = viewModel::reveal,
                    onAnswer = viewModel::answer,
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun ArticleBanner(onClick: () -> Unit) {
    Card(
        onClick = onClick,
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = PrimaryContainer)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.AutoMirrored.Filled.Article, contentDescription = null, tint = Primary)
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 10.dp)
            ) {
                Text("每日文章", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text("用今天的词读一篇短文", fontSize = 12.sp, color = TextSecondary)
            }
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowRight,
                contentDescription = null,
                tint = TextSecondary
            )
        }
    }
}

@Composable
private fun ReviewBody(
    state: ReviewUiState,
    onReveal: () -> Unit,
    onAnswer: (Boolean) -> Unit,
    modifier: Modifier = Modifier
) {
    val total = state.cards.size
    val safeIndex = state.index.coerceIn(0, (total - 1).coerceAtLeast(0))

    Column(modifier = modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = "第 ${(state.index + 1).coerceAtMost(total)} / $total 张",
                fontSize = 13.sp,
                color = TextSecondary,
                modifier = Modifier.weight(1f)
            )
            Text(text = "点击卡片查看释义", fontSize = 13.sp, color = TextSecondary)
        }
        Spacer(Modifier.height(8.dp))
        LinearProgressIndicator(
            progress = { (state.index + 1).toFloat() / total.coerceAtLeast(1) },
            modifier = Modifier
                .fillMaxWidth()
                .height(4.dp),
            color = Primary,
            trackColor = PrimaryContainer
        )
        Spacer(Modifier.height(12.dp))

        Box(modifier = Modifier.weight(1f)) {
            AnimatedContent(
                targetState = safeIndex,
                transitionSpec = {
                    (slideInHorizontally(animationSpec = tween(220)) { width -> width / 3 } + fadeIn(tween(220)))
                        .togetherWith(
                            slideOutHorizontally(animationSpec = tween(220)) { width -> -width / 3 } + fadeOut(tween(220))
                        )
                },
                label = "word-card"
            ) { index ->
                state.cards.getOrNull(index)?.let { card ->
                    WordCard(card = card, revealed = state.revealed, onClick = onReveal)
                }
            }
        }

        Spacer(Modifier.height(14.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            OutlinedButton(
                onClick = { onAnswer(false) },
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Danger)
            ) {
                Text("不认识", fontSize = 16.sp)
            }
            Button(
                onClick = { onAnswer(true) },
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Success)
            ) {
                Text("认识", fontSize = 16.sp)
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun WordCard(
    card: WordEntity,
    revealed: Boolean,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxSize()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = card.word,
                fontSize = 40.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center
            )
            if (card.phonetic.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(text = card.phonetic, fontSize = 16.sp, color = TextSecondary)
            }
            Spacer(Modifier.height(24.dp))
            if (!revealed) {
                Text(
                    text = "点击卡片查看释义",
                    fontSize = 13.sp,
                    color = TextSecondary
                )
            } else {
                HorizontalDivider(color = DividerColor)
                Spacer(Modifier.height(16.dp))
                Text(
                    text = card.meaning.ifBlank { "-" },
                    fontSize = 18.sp,
                    lineHeight = 27.sp,
                    textAlign = TextAlign.Center
                )
                if (card.example.isNotBlank()) {
                    Spacer(Modifier.height(14.dp))
                    Text(
                        text = card.example,
                        fontSize = 14.sp,
                        lineHeight = 21.sp,
                        color = TextSecondary,
                        fontStyle = FontStyle.Italic,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }
    }
}

@Composable
private fun FinishedRound(
    total: Int,
    onRestart: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Filled.CheckCircle,
            contentDescription = null,
            tint = Success,
            modifier = Modifier.size(56.dp)
        )
        Spacer(Modifier.height(16.dp))
        Text(text = "今天复习完成", fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text(text = "共完成 $total 个单词", fontSize = 13.sp, color = TextSecondary)
        Spacer(Modifier.height(24.dp))
        Button(
            onClick = onRestart,
            modifier = Modifier
                .width(160.dp)
                .height(48.dp),
            shape = RoundedCornerShape(12.dp)
        ) {
            Text("再来一轮")
        }
    }
}
