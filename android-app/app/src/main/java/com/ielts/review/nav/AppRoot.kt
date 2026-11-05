package com.ielts.review.nav

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.AddCircleOutline
import androidx.compose.material.icons.filled.School
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.ielts.review.IeltsApp
import com.ielts.review.ui.article.ArticleScreen
import com.ielts.review.ui.article.ArticleViewModel
import com.ielts.review.ui.common.OfflineBanner
import com.ielts.review.ui.detail.WordDetailScreen
import com.ielts.review.ui.detail.WordDetailViewModel
import com.ielts.review.ui.input.InputScreen
import com.ielts.review.ui.input.InputViewModel
import com.ielts.review.ui.library.LibraryScreen
import com.ielts.review.ui.library.LibraryViewModel
import com.ielts.review.ui.review.ReviewScreen
import com.ielts.review.ui.review.ReviewViewModel
import com.ielts.review.ui.settings.SettingsScreen
import com.ielts.review.ui.settings.SettingsViewModel

private object Routes {
    const val REVIEW = "review"
    const val LIBRARY = "library"
    const val INPUT = "input"
    const val SETTINGS = "settings"
    const val ARTICLE = "article"
    const val DETAIL = "detail/{id}"

    fun detail(id: Long) = "detail/$id"
}

private data class TabItem(
    val route: String,
    val label: String,
    val icon: ImageVector
)

private val tabs = listOf(
    TabItem(Routes.REVIEW, "复习", Icons.Filled.School),
    TabItem(Routes.LIBRARY, "单词本", Icons.AutoMirrored.Filled.MenuBook),
    TabItem(Routes.INPUT, "录入", Icons.Filled.AddCircleOutline)
)

@Composable
fun AppRoot() {
    val container = (LocalContext.current.applicationContext as IeltsApp).container
    val navController = rememberNavController()
    val online by container.networkMonitor.isOnline.collectAsStateWithLifecycle(
        initialValue = container.networkMonitor.isCurrentlyOnline()
    )
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = tabs.any { it.route == currentRoute }

    Scaffold(
        containerColor = Color.White,
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(containerColor = Color.White) {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute == tab.route,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) }
                        )
                    }
                }
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            if (!online) {
                OfflineBanner()
            }
            NavHost(
                navController = navController,
                startDestination = Routes.REVIEW,
                modifier = Modifier.weight(1f)
            ) {
                composable(Routes.REVIEW) {
                    val viewModel: ReviewViewModel = viewModel(
                        factory = ReviewViewModel.factory(container)
                    )
                    ReviewScreen(
                        viewModel = viewModel,
                        onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                        onOpenArticle = { navController.navigate(Routes.ARTICLE) }
                    )
                }

                composable(Routes.LIBRARY) {
                    val viewModel: LibraryViewModel = viewModel(
                        factory = LibraryViewModel.factory(container)
                    )
                    LibraryScreen(
                        viewModel = viewModel,
                        onOpenDetail = { id -> navController.navigate(Routes.detail(id)) },
                        onOpenSettings = { navController.navigate(Routes.SETTINGS) }
                    )
                }

                composable(Routes.INPUT) {
                    val viewModel: InputViewModel = viewModel(
                        factory = InputViewModel.factory(container)
                    )
                    InputScreen(viewModel = viewModel)
                }

                composable(
                    route = Routes.DETAIL,
                    arguments = listOf(navArgument("id") { type = NavType.LongType })
                ) { entry ->
                    val id = entry.arguments?.getLong("id") ?: 0L
                    val viewModel: WordDetailViewModel = viewModel(
                        factory = WordDetailViewModel.factory(container, id)
                    )
                    WordDetailScreen(
                        viewModel = viewModel,
                        onBack = { navController.popBackStack() }
                    )
                }

                composable(Routes.ARTICLE) {
                    val viewModel: ArticleViewModel = viewModel(
                        factory = ArticleViewModel.factory(container)
                    )
                    ArticleScreen(
                        viewModel = viewModel,
                        onBack = { navController.popBackStack() }
                    )
                }

                composable(Routes.SETTINGS) {
                    val viewModel: SettingsViewModel = viewModel(
                        factory = SettingsViewModel.factory(container)
                    )
                    SettingsScreen(
                        viewModel = viewModel,
                        onBack = { navController.popBackStack() }
                    )
                }
            }
        }
    }
}
