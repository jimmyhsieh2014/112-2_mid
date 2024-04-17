package im.ntub.myapplicationactivity

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.CheckBox
import androidx.appcompat.app.AppCompatActivity
import im.ntub.myapplicationactivity.databinding.ActivitySecBinding

class SecActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySecBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySecBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnCal.setOnClickListener {
            showConfirmationDialog()
        }

        binding.btnReset.setOnClickListener {
            // Reset all selections
            binding.drink1RadioGroup.clearCheck()
            binding.drink2RadioGroup.clearCheck()
            binding.chbFr.isChecked = false
            binding.chbNu.isChecked = false
            binding.chbCr.isChecked = false
            binding.editName.text.clear()
        }
    }

    private fun showConfirmationDialog() {
        val alertDialogBuilder = AlertDialog.Builder(this)
        alertDialogBuilder.setTitle("確認訂單")
        alertDialogBuilder.setMessage("您確定要結帳嗎？")

        alertDialogBuilder.setPositiveButton("確認") { dialog, which ->
            val total = calculateTotal()
            val name = binding.editName.text.toString()
            val chooseMainCourse = getSelectedText(binding.drink1RadioGroup)
            val chooseDrink = getSelectedText(binding.drink2RadioGroup)
            val selectedSnacks = getSelectedSnacksText()

            val intent = Intent().apply {
                putExtra("name", name)
                putExtra("mainCourse", chooseMainCourse)
                putExtra("drink", chooseDrink)
                putExtra("snacks", selectedSnacks)
                putExtra("total", total)
            }

            setResult(Activity.RESULT_OK, intent)
            finish()
        }

        alertDialogBuilder.setNegativeButton("取消") { dialog, which ->
            dialog.dismiss()
        }

        val alertDialog = alertDialogBuilder.create()
        alertDialog.show()
    }

    private fun getSelectedText(radioGroup: RadioGroup): String {
        val checkedRadioButtonId = radioGroup.checkedRadioButtonId
        return findViewById<RadioButton>(checkedRadioButtonId)?.text?.toString() ?: ""
    }

    private fun getSelectedSnacksText(): String {
        val selectedSnacks = mutableListOf<String>()

        if (binding.chbFr.isChecked) {
            selectedSnacks.add("薯條")
        }
        if (binding.chbNu.isChecked) {
            selectedSnacks.add("雞塊")
        }
        if (binding.chbCr.isChecked) {
            selectedSnacks.add("冰淇淋")
        }
        return selectedSnacks.joinToString(", ")
    }




    private fun calculateTotal(): Int {
        var total = 0
        // Calculate total based on selections
        total += when (binding.drink1RadioGroup.checkedRadioButtonId) {
            R.id.radioButton1, R.id.radioButton2, R.id.radioButton3 -> 130
            R.id.radioButton4, R.id.radioButton5 -> 20
            else -> 0
        }
        total += when (binding.drink2RadioGroup.checkedRadioButtonId) {
            R.id.radioButton4, R.id.radioButton5 -> 20
            else -> 0
        }
        total += if (binding.chbFr.isChecked) 50 else 0
        total += if (binding.chbNu.isChecked) 50 else 0
        total += if (binding.chbCr.isChecked) 50 else 0

        return total
    }
}
