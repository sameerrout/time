package com.ttl.scanner

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.ttl.scanner.ui.history.HistoryScreen
import com.ttl.scanner.ui.history.HistoryViewModel
import com.ttl.scanner.ui.home.HomeScreen
import com.ttl.scanner.ui.home.HomeViewModel
import com.ttl.scanner.ui.navigation.Screen
import com.ttl.scanner.ui.pairing.PairingScreen
import com.ttl.scanner.ui.pairing.PairingViewModel
import com.ttl.scanner.ui.scanner.ScannerScreen
import com.ttl.scanner.ui.scanner.ScannerViewModel
import com.ttl.scanner.ui.settings.SettingsScreen
import com.ttl.scanner.ui.settings.SettingsViewModel
import com.ttl.scanner.ui.theme.TTLScannerTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as ScannerApp
        val isAlreadyPaired = app.preferenceManager.isPaired()

        setContent {
            TTLScannerTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    AppNavigation(
                        app = app,
                        startDestination = if (isAlreadyPaired) Screen.Home.route else Screen.Pairing.route
                    )
                }
            }
        }
    }
}

@Composable
fun AppNavigation(
    app: ScannerApp,
    startDestination: String
) {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = startDestination) {
        composable(Screen.Pairing.route) {
            val viewModel = PairingViewModel(
                prefManager = app.preferenceManager,
                networkClient = app.networkClient,
                materialRepository = app.materialRepository
            )
            PairingScreen(
                viewModel = viewModel,
                onPairingSuccess = {
                    navController.navigate(Screen.Home.route) {
                        popUpTo(Screen.Pairing.route) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.Home.route) {
            val viewModel = HomeViewModel(
                prefManager = app.preferenceManager,
                networkClient = app.networkClient,
                materialRepository = app.materialRepository,
                scanRepository = app.scanRepository,
                database = app.database
            )
            HomeScreen(
                viewModel = viewModel,
                onOpenIssueScanner = {
                    navController.navigate(Screen.Scanner.createRoute("ISSUE"))
                },
                onOpenReceiveScanner = {
                    navController.navigate(Screen.Scanner.createRoute("RECEIVE"))
                },
                onOpenHistory = {
                    navController.navigate(Screen.History.route)
                },
                onOpenSettings = {
                    navController.navigate(Screen.Settings.route)
                }
            )
        }

        composable(
            route = Screen.Scanner.route,
            arguments = listOf(navArgument("mode") { type = NavType.StringType })
        ) { backStackEntry ->
            val mode = backStackEntry.arguments?.getString("mode") ?: "ISSUE"
            val viewModel = ScannerViewModel(
                mode = mode,
                materialRepository = app.materialRepository,
                scanRepository = app.scanRepository,
                soundManager = app.soundManager
            )
            ScannerScreen(
                viewModel = viewModel,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(Screen.History.route) {
            val viewModel = HistoryViewModel(
                scanRepository = app.scanRepository
            )
            HistoryScreen(
                viewModel = viewModel,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(Screen.Settings.route) {
            val viewModel = SettingsViewModel(
                prefManager = app.preferenceManager,
                database = app.database
            )
            SettingsScreen(
                viewModel = viewModel,
                onNavigateBack = { navController.popBackStack() },
                onUnpaired = {
                    navController.navigate(Screen.Pairing.route) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }
    }
}
