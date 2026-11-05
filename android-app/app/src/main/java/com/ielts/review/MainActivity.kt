package com.ielts.review

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.ielts.review.nav.AppRoot
import com.ielts.review.ui.theme.IeltsTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            IeltsTheme {
                AppRoot()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        (application as IeltsApp).container.requestSync()
    }
}
