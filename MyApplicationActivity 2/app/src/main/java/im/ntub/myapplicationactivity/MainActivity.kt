package im.ntub.myapplicationactivity

import android.app.Activity
import android.content.Intent
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import im.ntub.myapplicationactivity.databinding.ActivityMainBinding

//11056026 謝定衡 11056048 張予綸

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private var name = ""
    private var isChecked = false

    private val launcher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                val data = result.data
                val yourname = data?.getStringExtra("name")
                val chooseMainCourse = data?.getStringExtra("mainCourse")
                val chooseDrink = data?.getStringExtra("drink")
                val chooseSnacks = data?.getStringExtra("snacks")
                val calculateTotal = data?.getIntExtra("total", 0)

                binding.textViewNamebox.text = yourname
                binding.TextViewMainCourse1.text = chooseMainCourse
                binding.textViewDrink1.text = chooseDrink
                binding.textViewSnack1.text = chooseSnacks ?: ""
                binding.textViewMoney.text = "總金額：$calculateTotal"
            } else {
                binding.TextViewMainCourse1.text = ""
                binding.textViewDrink1.text = ""
                binding.textViewSnack1.text = ""
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnOpen.setOnClickListener {
            val intent = Intent(this, SecActivity::class.java)
            launcher.launch(intent)
        }
    }
}