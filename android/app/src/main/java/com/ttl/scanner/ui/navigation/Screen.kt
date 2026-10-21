package com.ttl.scanner.ui.navigation

sealed class Screen(val route: String) {
    object Pairing : Screen("pairing")
    object Home : Screen("home")
    object Scanner : Screen("scanner/{mode}") {
        fun createRoute(mode: String) = "scanner/${mode.uppercase()}"
    }
    object History : Screen("history")
    object Settings : Screen("settings")
}
