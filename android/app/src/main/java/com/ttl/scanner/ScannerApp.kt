package com.ttl.scanner

import android.app.Application
import com.ttl.scanner.data.api.NetworkClient
import com.ttl.scanner.data.local.AppDatabase
import com.ttl.scanner.data.pref.PreferenceManager
import com.ttl.scanner.data.repository.MaterialRepository
import com.ttl.scanner.data.repository.ScanRepository
import com.ttl.scanner.sync.SyncScheduler
import com.ttl.scanner.util.SoundManager

class ScannerApp : Application() {

    lateinit var preferenceManager: PreferenceManager
        private set
    lateinit var networkClient: NetworkClient
        private set
    lateinit var database: AppDatabase
        private set
    lateinit var materialRepository: MaterialRepository
        private set
    lateinit var scanRepository: ScanRepository
        private set
    lateinit var soundManager: SoundManager
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this

        preferenceManager = PreferenceManager(this)
        networkClient = NetworkClient(preferenceManager)
        database = AppDatabase.getInstance(this)
        materialRepository = MaterialRepository(database.materialDao(), networkClient, preferenceManager)
        scanRepository = ScanRepository(database.scanEventDao(), networkClient, preferenceManager)
        soundManager = SoundManager(this)

        SyncScheduler.schedulePeriodicSync(this)
    }

    companion object {
        lateinit var instance: ScannerApp
            private set
    }
}
