import louis
text = "في زَمانٍ بعيدٍ، اجتمعَ الأصدقاءُ الأربعةُ..."
# Inverser le texte arabe pour la conversion LibLouis
text_reversed = text[::-1]
braille = louis.translate(["ar-ar-g1.utb"], text_reversed)
print(braille[0]) 