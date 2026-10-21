package com.ttl.scanner.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.ttl.scanner.ScannerApp

class ScanSyncWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val app = applicationContext as ScannerApp
        val repo = app.scanRepository

        return try {
            val delivered = repo.syncPendingQueue()
            repo.pollSentScans()

            // If there are still pending scans, ask WorkManager to retry with exponential backoff
            val remaining = app.database.scanEventDao().getPendingScans()
            if (remaining.isNotEmpty()) {
                Result.retry()
            } else {
                Result.success()
            }
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
