package com.ielts.review.util

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

object TimeUtil {

    private val FORMAT: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    /** 后端要求的 "yyyy-MM-dd HH:mm:ss" */
    fun now(): String = FORMAT.format(LocalDateTime.now())

    fun today(): String = LocalDateTime.now().toLocalDate().toString()
}
