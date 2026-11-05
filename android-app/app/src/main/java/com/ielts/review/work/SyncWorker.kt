package com.ielts.review.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.ielts.review.IeltsApp

class SyncWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as? IeltsApp ?: return Result.success()
        runCatching { app.container.syncRepository.sync() }
        return Result.success()
    }

    companion object {
        const val PERIODIC_NAME = "ielts-periodic-sync"
        const val ONE_SHOT_NAME = "ielts-sync-now"
    }
}
